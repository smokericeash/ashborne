from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings


class EventBroker:
    """SSE broker with optional Redis fan-out and an in-process fallback."""

    def __init__(self, max_queue_size: int = 100, redis_url: str | None = None) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._instance_id = str(uuid.uuid4())
        self._redis = None
        self._channel = "ashborne:events:v1"
        if redis_url:
            try:
                from redis.asyncio import from_url

                self._redis = from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=2.0,
                    health_check_interval=30,
                )
            except Exception:
                logging.getLogger("ashborne.events").warning("Redis unavailable; SSE is limited to this process")

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "event": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        if self._redis is not None:
            try:
                envelope = {"origin": self._instance_id, "event": event}
                await self._redis.publish(self._channel, json.dumps(envelope, separators=(",", ":")))
            except Exception:
                logging.getLogger("ashborne.events").warning("Redis event publish failed; local delivery continues")

    async def _read_redis(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if self._redis is None:
            return
        retry_delay = 0.25
        while True:
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            try:
                await pubsub.subscribe(self._channel)
                retry_delay = 0.25
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        envelope = json.loads(message["data"])
                        if envelope.get("origin") == self._instance_id:
                            continue
                        event = envelope["event"]
                        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
                            continue
                    except (KeyError, TypeError, json.JSONDecodeError):
                        continue
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    queue.put_nowait(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.getLogger("ashborne.events").warning(
                    "Redis event subscription interrupted; local delivery continues while reconnection is attempted"
                )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
            finally:
                with suppress(Exception):
                    await pubsub.aclose()

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self._max_queue_size)
        redis_reader = asyncio.create_task(self._read_redis(queue), name="ashborne-redis-event-reader")
        async with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {"event": "keepalive", "data": {}, "timestamp": datetime.now(UTC).isoformat()}
        finally:
            redis_reader.cancel()
            try:
                await redis_reader
            except asyncio.CancelledError:
                pass
            async with self._lock:
                self._subscribers.discard(queue)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()


event_broker = EventBroker(redis_url=get_settings().redis_url)
