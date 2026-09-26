"""Sliding-window rate limits.

Protects sign-in endpoints from guessing and credential stuffing, the chat from runaway
model costs, and uploads from floods. State is in memory, so limits apply per API process;
running several replicas needs a shared store (e.g. Redis) behind the same interface.
"""

import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from observability import RATE_LIMITED

# name -> (requests, per seconds)
LIMITS = {
    "session": (10, 60),       # creating sessions (bank or demo), per client
    "auth_failure": (20, 60),  # rejected API keys / tokens, per client
    "chat": (20, 60),          # chat questions, per customer
    "upload": (30, 60),        # statement uploads, per bank
    "export": (5, 60),         # data exports, per customer or bank
}


class RateLimiter:
    def __init__(self, limits: dict[str, tuple[int, int]] | None = None):
        self.limits = limits or LIMITS
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, name: str, key: str) -> None:
        """Record a hit; raise 429 with Retry-After when the limit is exceeded."""
        if os.getenv("NARRAI_RATE_LIMITS", "1") != "1":
            return
        limit, window = self.limits[name]
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(name, key)]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                RATE_LIMITED.labels(name).inc()
                retry_after = max(1, math.ceil(hits[0] + window - now))
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_key(request: Request) -> str:
    """The caller's address. Only trusts X-Forwarded-For when a trusted proxy sets it (NARRAI_TRUST_PROXY=1)."""
    if os.getenv("NARRAI_TRUST_PROXY", "0") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
