"""
Per-student rate limiting with sliding window.
"""

import time
from collections import defaultdict
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.shared.config import settings
from src.shared.logging import get_logger

logger = get_logger(__name__)


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter per student."""

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        # student_id -> list of request timestamps in window
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _prune(self, student_id: str):
        """Remove timestamps older than window."""
        now = time.time()
        cutoff = now - self.window_seconds
        self._requests[student_id] = [t for t in self._requests[student_id] if t > cutoff]

    def is_allowed(self, student_id: str) -> bool:
        """Check if request is allowed."""
        self._prune(student_id)
        return len(self._requests[student_id]) < self.requests_per_minute

    def record(self, student_id: str):
        """Record a request."""
        self._requests[student_id].append(time.time())

    def retry_after_seconds(self, student_id: str) -> int:
        """Seconds until next request allowed (oldest in window expires)."""
        self._prune(student_id)
        if len(self._requests[student_id]) < self.requests_per_minute:
            return 0
        # Oldest request in window
        oldest = min(self._requests[student_id])
        return max(1, int(self.window_seconds - (time.time() - oldest)))


def get_student_id(request: Request) -> Optional[str]:
    """Extract student ID from request for rate limiting."""
    # Prefer Authorization header (Bearer token with student claim) or cookie
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        # For now, use raw token as identifier until we have JWT parsing (Task 23)
        return f"bearer:{auth[7:][:64]}"
    # Cookie-based (session token)
    session_token = request.cookies.get("tai_session")
    if session_token:
        return f"session:{session_token[:64]}"
    # Fallback: use client IP when no auth (rate limit per IP for unauthenticated)
    client = request.client
    if client:
        return f"ip:{client.host}"
    # TestClient/ASGI may not set client; use X-Rate-Limit-Key for testing
    rate_key = request.headers.get("X-Rate-Limit-Key")
    if rate_key:
        return f"key:{rate_key[:64]}"
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-student rate limiting middleware."""

    def __init__(
        self,
        app,
        requests_per_minute: Optional[int] = None,
        skip_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(
            requests_per_minute
            or getattr(settings.api, "rate_limit_requests_per_minute", 30)
        )
        self.skip_paths = set(skip_paths or ["/health", "/docs", "/openapi.json", "/redoc"])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in self.skip_paths or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        student_id = get_student_id(request)
        if not student_id:
            # No identifier — allow (e.g. health checks, docs)
            return await call_next(request)

        if not self.limiter.is_allowed(student_id):
            retry_after = self.limiter.retry_after_seconds(student_id)
            logger.warning(
                "Rate limit exceeded",
                extra={"student_id": student_id[:8], "retry_after": retry_after},
            )
            return Response(
                content='{"detail":"Rate limit exceeded. Try again later."}',
                status_code=429,
                headers={"Retry-After": str(retry_after), "Content-Type": "application/json"},
            )

        self.limiter.record(student_id)
        return await call_next(request)
