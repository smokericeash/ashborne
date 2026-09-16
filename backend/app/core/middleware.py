from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_context


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        incoming = request.headers.get("x-request-id", "")
        request_id = (
            incoming
            if incoming and len(incoming) <= 64 and all(c.isalnum() or c in "-_" for c in incoming)
            else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_context.reset(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        response = await call_next(request)
        content_security_policy = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path == "/docs":
            # FastAPI's development Swagger page pins its assets to jsDelivr.
            # Interactive docs are disabled entirely in production below.
            content_security_policy = (
                "default-src 'none'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            )
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Content-Security-Policy": content_security_policy,
            "Cache-Control": "no-store" if request.url.path.startswith("/api/") else "no-cache",
        }
        for key, value in headers.items():
            response.headers.setdefault(key, value)
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        length = headers.get(b"content-length")
        if length:
            try:
                parsed_length = int(length)
                if parsed_length < 0:
                    await self._reject(scope, receive, send, 400, "invalid content length")
                    return
                if parsed_length > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid content length")
                return

        if scope.get("method", "GET").upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return

        # Buffer body-bearing requests up to the configured cap before invoking
        # the framework. Raising from receive() is insufficient because request
        # parsers can translate that exception into an incorrect generic 400.
        messages: list[Message] = []
        consumed = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                if message.get("more_body", False):
                    continue
            break

        message_index = 0

        async def replay_receive() -> Message:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status: int = 413,
        detail: str = "request body too large",
    ) -> None:
        response = JSONResponse({"detail": detail}, status_code=status)
        await response(scope, receive, send)


class InMemoryRateLimiter:
    """Bounded sliding-window limiter used directly and as Redis fallback."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int(window_seconds - (now - bucket[0])))
                return False, retry
            bucket.append(now)
            if len(self._buckets) > 20_000:
                empty = [name for name, values in self._buckets.items() if not values or values[-1] <= cutoff]
                for name in empty[:5_000]:
                    self._buckets.pop(name, None)
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        requests: int,
        window_seconds: int,
        login_requests: int,
        redis_url: str | None = None,
    ) -> None:
        super().__init__(app)
        self.requests = requests
        self.window_seconds = window_seconds
        self.login_requests = login_requests
        self.limiter = InMemoryRateLimiter()
        self.redis = None
        if redis_url:
            try:
                from redis.asyncio import from_url

                self.redis = from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=2.0,
                    health_check_interval=30,
                )
            except Exception:
                logging.getLogger("kandor.rate_limit").warning("Redis unavailable; using in-process rate limiting")

    async def _allow(self, key: str, limit: int) -> tuple[bool, int]:
        if self.redis is not None:
            epoch = int(time.time())
            bucket = epoch // self.window_seconds
            redis_key = f"kandor:rate:{key}:{bucket}"
            try:
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.incr(redis_key)
                    pipe.expire(redis_key, self.window_seconds + 1)
                    count, _ = await pipe.execute()
                retry = self.window_seconds - (epoch % self.window_seconds)
                return int(count) <= limit, max(1, retry)
            except Exception:
                logging.getLogger("kandor.rate_limit").warning("Redis rate limiter failed; using local fallback")
        return await self.limiter.allow(key, limit, self.window_seconds)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable]):
        if request.url.path.startswith("/health/"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        login = request.url.path.rstrip("/") == "/api/v1/auth/login"
        limit = self.login_requests if login else self.requests
        category = "login" if login else "api"
        allowed, retry_after = await self._allow(f"{category}:{ip}", limit)
        if not allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(limit))
        return response
