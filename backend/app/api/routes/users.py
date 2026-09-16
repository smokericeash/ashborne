from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import admin_user, pagination_limit
from app.auth.security import hash_password
from app.core.database import get_db
from app.core.time import utcnow
from app.models import RefreshToken, RoleName, User
from app.schemas import UserCreate, UserList, UserResponse, UserUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserList)
async def list_users(
    search: str | None = Query(default=None, max_length=120),
    role: RoleName | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Depends(pagination_limit),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(admin_user),
) -> UserList:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(pattern), User.display_name.ilike(pattern)))
    if role:
        filters.append(User.role == role)
    total = (await db.execute(select(func.count(User.id)).where(*filters))).scalar_one()
    rows = (
        (await db.execute(select(User).where(*filters).order_by(User.created_at.desc()).offset(skip).limit(limit)))
        .scalars()
        .all()
    )
    return UserList(items=[UserResponse.model_validate(row) for row in rows], total=total, skip=skip, limit=limit)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> User:
    if (await db.execute(select(User.id).where(User.email == str(payload.email)))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="a user with this email already exists")
    user = User(
        email=str(payload.email),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password.get_secret_value()),
        role=payload.role,
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db,
        "USER_CREATED",
        request=request,
        user_id=actor.id,
        metadata={"target_user_id": user.id, "role": user.role.value},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(admin_user)) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def _ensure_another_admin(db: AsyncSession, target: User) -> None:
    if target.role != RoleName.ADMINISTRATOR or not target.is_active:
        return
    count = (
        await db.execute(
            select(func.count(User.id)).where(
                User.role == RoleName.ADMINISTRATOR, User.is_active.is_(True), User.id != target.id
            )
        )
    ).scalar_one()
    if count == 0:
        raise HTTPException(status_code=409, detail="cannot remove or demote the last active administrator")


async def _revoke_user_sessions(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if (payload.role is not None and payload.role != user.role) or payload.is_active is False:
        await _ensure_another_admin(db, user)
    changes = payload.model_dump(exclude_unset=True)
    old_role = user.role
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False:
        await _revoke_user_sessions(db, user.id)
    event_type = "USER_ROLE_CHANGED" if "role" in changes and old_role != user.role else "USER_UPDATED"
    await record_audit(
        db,
        event_type,
        request=request,
        user_id=actor.id,
        metadata={"target_user_id": user.id, "changes": {k: str(v) for k, v in changes.items()}},
    )
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(admin_user),
) -> Response:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    await _ensure_another_admin(db, user)
    user.is_active = False
    await _revoke_user_sessions(db, user.id)
    await record_audit(db, "USER_DEACTIVATED", request=request, user_id=actor.id, metadata={"target_user_id": user.id})
    await db.commit()
    return Response(status_code=204)
