"""
Catalyst API middleware — authentication and rate limiting.

TokenAuthMiddleware
-------------------
1.  Reads ``CATALYST_API_TOKENS`` from Django settings.
    If absent or empty, authentication is **disabled** for friction-free
    local development.

2.  For every ``/api/`` request, checks for a bearer token::

        Authorization: Bearer <token>

3.  Returns 401 if the token is missing or invalid.

4.  Non-API paths are not gated (admin, HTML views, media).

RateLimitMiddleware (SEC-025)
-----------------------------
Simple in-memory sliding-window rate limiter for ``/api/`` paths.

* Separate limits for **read** (GET/HEAD/OPTIONS) and **write**
  (POST/PUT/PATCH/DELETE) requests.
* Keyed by client IP (``REMOTE_ADDR``).
* Returns 429 with ``Retry-After`` header when exceeded.

Configuration (settings.py)::

    RATE_LIMIT_READ  = "200/minute"   # max GET requests per IP per minute
    RATE_LIMIT_WRITE = "30/minute"    # max write requests per IP per minute

Set either to ``"0/minute"`` or omit to disable that limit.
"""

import logging
import threading
import time

from django.conf import settings
from django.http import JsonResponse

logger = logging.getLogger("investigations.middleware")


class TokenAuthMiddleware:
    """Reject unauthenticated requests to ``/api/`` paths."""

    def __init__(self, get_response):
        self.get_response = get_response

        # Read allowed tokens once at startup for performance
        self.tokens: set[str] = set(getattr(settings, "CATALYST_API_TOKENS", []))
        self.require_auth: bool = getattr(settings, "CATALYST_REQUIRE_AUTH", False)

    # ------------------------------------------------------------------
    # Auth is "active" only when there are tokens configured, *or* when
    # the operator has explicitly turned on require_auth.
    # ------------------------------------------------------------------
    @property
    def _auth_active(self) -> bool:
        return bool(self.tokens) or self.require_auth

    def __call__(self, request):
        # Only gate /api/ paths. Healthcheck stays public because external probes
        # (Railway) don't send an Authorization header.
        if (
            request.path.startswith("/api/")
            and request.path != "/api/health/"
            and self._auth_active
        ):
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")

            if not auth_header:
                return JsonResponse(
                    {
                        "errors": {
                            "auth": ["Authentication required. Provide an Authorization header."]
                        }
                    },
                    status=401,
                )

            # Expect "Bearer <token>"
            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return JsonResponse(
                    {
                        "errors": {
                            "auth": [
                                "Invalid Authorization header format. Expected: Bearer <token>"
                            ]
                        }
                    },
                    status=401,
                )

            token = parts[1].strip()
            if token not in self.tokens:
                return JsonResponse(
                    {"errors": {"auth": ["Invalid or expired API token."]}},
                    status=401,
                )

            # Attach token to request so views can identify callers later
            request.api_token = token

        return self.get_response(request)


# -----------------------------------------------------------------------
# SEC-025: Rate Limiting Middleware
# -----------------------------------------------------------------------


def _parse_rate(rate_string: str) -> tuple[int, int]:
    """Parse a rate string like '200/minute' into (max_requests, window_seconds).

    Supported windows: second, minute, hour, day.
    Returns (0, 0) if parsing fails or rate is disabled.
    """
    if not rate_string:
        return 0, 0

    try:
        count_str, window = rate_string.strip().split("/", 1)
        count = int(count_str)
    except (ValueError, AttributeError):
        return 0, 0

    windows = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    window_seconds = windows.get(window.strip().lower(), 0)

    if count <= 0 or window_seconds <= 0:
        return 0, 0

    return count, window_seconds


class RateLimitMiddleware:
    """In-memory sliding-window rate limiter for /api/ paths.

    Tracks request timestamps per IP address in a thread-safe dict.
    Stale entries are cleaned up periodically to prevent memory leaks.

    This is suitable for single-process deployments.  For multi-process
    production setups, switch to a Redis-backed rate limiter.
    """

    # Cleanup old entries every N requests to prevent unbounded growth
    _CLEANUP_INTERVAL = 500

    def __init__(self, get_response):
        self.get_response = get_response

        # Parse rate limits from settings
        self.read_limit, self.read_window = _parse_rate(
            getattr(settings, "RATE_LIMIT_READ", "200/minute")
        )
        self.write_limit, self.write_window = _parse_rate(
            getattr(settings, "RATE_LIMIT_WRITE", "30/minute")
        )

        # Separate buckets for read vs write, keyed by IP
        # {ip: [timestamp, timestamp, ...]}
        self._read_log: dict[str, list[float]] = {}
        self._write_log: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._request_count = 0

    def _get_client_ip(self, request) -> str:
        """Return the real client IP, trusting X-Forwarded-For when behind a proxy.

        Railway (and most cloud platforms) prepend the real client IP as the
        first entry in X-Forwarded-For. REMOTE_ADDR alone would return the
        proxy IP, causing all users to share one rate-limit bucket.
        """
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _is_write_method(self, method: str) -> bool:
        return method in ("POST", "PUT", "PATCH", "DELETE")

    def _check_rate(
        self, log: dict[str, list[float]], ip: str, max_requests: int, window: int
    ) -> tuple[bool, int]:
        """Check if the request is within the rate limit.

        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        cutoff = now - window

        with self._lock:
            timestamps = log.get(ip, [])

            # Remove expired timestamps
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= max_requests:
                # Calculate how long until the oldest request expires
                retry_after = int(timestamps[0] - cutoff) + 1
                log[ip] = timestamps
                return False, retry_after

            timestamps.append(now)
            log[ip] = timestamps

        return True, 0

    def _maybe_cleanup(self) -> None:
        """Periodically purge stale IP entries to bound memory usage."""
        self._request_count += 1
        if self._request_count < self._CLEANUP_INTERVAL:
            return

        self._request_count = 0
        now = time.monotonic()

        with self._lock:
            for log, window in [
                (self._read_log, self.read_window),
                (self._write_log, self.write_window),
            ]:
                if not window:
                    continue
                cutoff = now - window
                stale_keys = [ip for ip, ts in log.items() if not ts or ts[-1] <= cutoff]
                for ip in stale_keys:
                    del log[ip]

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        ip = self._get_client_ip(request)
        is_write = self._is_write_method(request.method)

        # Pick the right bucket and limits
        if is_write and self.write_limit:
            allowed, retry_after = self._check_rate(
                self._write_log, ip, self.write_limit, self.write_window
            )
        elif not is_write and self.read_limit:
            allowed, retry_after = self._check_rate(
                self._read_log, ip, self.read_limit, self.read_window
            )
        else:
            allowed, retry_after = True, 0

        if not allowed:
            kind = "write" if is_write else "read"
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "ip": ip,
                    "method": request.method,
                    "path": request.path,
                    "kind": kind,
                },
            )
            response = JsonResponse(
                {
                    "errors": {
                        "rate_limit": [f"Too many requests. Try again in {retry_after} seconds."]
                    }
                },
                status=429,
            )
            response["Retry-After"] = str(retry_after)
            return response

        self._maybe_cleanup()
        return self.get_response(request)
