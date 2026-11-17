"""In-process sliding-window rate limiter.

This protects login and password-reset endpoints against brute force in a single
process. It is not a substitute for an edge/WAF limiter in a multi-instance
deployment, but it is cheap, dependency-free and correct for the project's
SQLite/local development target.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.core.exceptions import AppError
from app.core.security import hash_client_ip


class RateLimitExceeded(AppError):
    status_code = 429
    code = "rate_limited"


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                raise RateLimitExceeded(
                    "Too many attempts. Try again later.",
                    details={"retry_after_seconds": retry_after},
                )
            bucket.append(now)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


login_limiter = SlidingWindowLimiter()
reset_limiter = SlidingWindowLimiter()
mfa_limiter = SlidingWindowLimiter()


def client_key(request: Request, *, scope: str, principal: str | None = None) -> str:
    """A pseudonymous key scoped by operation, client and account.

    Neither the raw IP nor the raw email is stored in the shared counter table.
    The fixed digest is not a secret; it prevents casual account disclosure in
    operational database reads while preserving per-account aggregation.
    """
    ip_hash = hash_client_ip(request.client.host if request.client else None) or "unknown"
    identity = principal.strip().lower() if principal else "-"
    return f"{scope}:{ip_hash}:{_principal_digest(identity)}"


def account_key(scope: str, principal: str) -> str:
    """Account-only key so one account cannot evade limits by changing IP."""
    identity = principal.strip().lower()
    return f"{scope}:account:{_principal_digest(identity)}"


def _principal_digest(identity: str) -> str:
    return hashlib.sha256(
        f"loopmesh.security-principal.v1:{identity}".encode("utf-8")
    ).hexdigest()[:32]
