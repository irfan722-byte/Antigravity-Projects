"""Minimal in-memory rate limiter (per client IP + bucket). Redis-backed variant is a drop-in for multi-instance deployments."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, default_per_minute: int = 120):
        self.default = default_per_minute
        self._hits: dict[str, deque] = defaultdict(deque)

    def _key(self, request: Request, bucket: str) -> str:
        ip = request.client.host if request.client else "unknown"
        return f"{bucket}:{ip}"

    def check(self, request: Request, bucket: str = "default", per_minute: int | None = None) -> None:
        limit = per_minute or self.default
        now = time.monotonic()
        dq = self._hits[self._key(request, bucket)]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(429, f"rate limit exceeded for {bucket}")
        dq.append(now)
