from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, unauthorized
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    sha256,
    verify_password,
)
from app.core.database import get_db
from app.core.time import ensure_utc, utcnow
from app.models import RefreshToken, User
from app.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse, UserResponse
from app.services.audit import record_audit
from app.services.settings import read_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
_dummy_password_hash = hash_password("Kandor-Dummy-Password-2026")


async def _issue_tokens(db: AsyncSession, user: User, family_id: str | None = None) -> TokenResponse:
    runtime_settings = await read_settings(db)
    access, expires_in = create_access_token(
        user.id, user.role.value, expires_minutes=runtime_settings.session_timeout_minutes
    )
    refresh, jti, family, expires_at = create_refresh_token(user.id, family_id)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti_hash=sha256(jti),
            family_id=family,
            expires_at=expires_at,
        )
    )
    await db.flush()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = (await db.execute(select(User).where(User.email == str(payload.email)))).scalar_one_or_none()
    valid = verify_password(payload.password.get_secret_value(), user.password_hash if user else _dummy_password_hash)
    if not user or not valid or not user.is_active:
        await record_audit(
            db,
            "USER_LOGIN_FAILURE",
            request=request,
            user_id=user.id if user else None,
            metadata={"email": str(payload.email), "reason": "invalid_credentials"},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="invalid email or password", headers={"WWW-Authenticate": "Bearer"})
    user.last_login_at = utcnow()
    response = await _issue_tokens(db, user)
    await record_audit(db, "USER_LOGIN_SUCCESS", request=request, user_id=user.id)
    await db.commit()
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    raw = payload.refresh_token.get_secret_value()
    try:
        claims = decode_token(raw, "refresh")
    except jwt.PyJWTError as exc:
        raise unauthorized("invalid or expired refresh token") from exc
    token_row = (
        await db.execute(
            select(RefreshToken).where(RefreshToken.jti_hash == sha256(str(claims["jti"]))).with_for_update()
        )
    ).scalar_one_or_none()
    now = utcnow()
    if not token_row:
        raise unauthorized("refresh token is not recognized")
    if token_row.used_at or token_row.revoked_at:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token_row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await record_audit(
            db,
            "REFRESH_TOKEN_REUSE_DETECTED",
            request=request,
            user_id=token_row.user_id,
            metadata={"family_id": token_row.family_id},
        )
        await db.commit()
        raise unauthorized("refresh token reuse detected; session revoked")
    if ensure_utc(token_row.expires_at) <= now or token_row.user_id != claims.get("sub"):
        token_row.revoked_at = now
        await db.commit()
        raise unauthorized("refresh token is invalid or expired")
    user = await db.get(User, token_row.user_id)
    if not user or not user.is_active:
        token_row.revoked_at = now
        await db.commit()
        raise unauthorized("user is inactive or unavailable")
    token_row.used_at = now
    response = await _issue_tokens(db, user, token_row.family_id)
    replacement = (
        (
            await db.execute(
                select(RefreshToken)
                .where(
                    RefreshToken.family_id == token_row.family_id,
                    RefreshToken.used_at.is_(None),
                    RefreshToken.id != token_row.id,
                )
                .order_by(RefreshToken.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if replacement:
        token_row.replaced_by_id = replacement.id
    await record_audit(db, "SESSION_REFRESHED", request=request, user_id=user.id)
    await db.commit()
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        claims = decode_token(payload.refresh_token.get_secret_value(), "refresh")
    except jwt.PyJWTError:
        return Response(status_code=204)
    token_row = (
        await db.execute(select(RefreshToken).where(RefreshToken.jti_hash == sha256(str(claims["jti"]))))
    ).scalar_one_or_none()
    if token_row:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == token_row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await record_audit(db, "USER_LOGOUT", request=request, user_id=token_row.user_id)
        await db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
