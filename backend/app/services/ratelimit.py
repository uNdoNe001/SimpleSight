"""Per-provider rate limiting and usage accounting (SMPLSGHT-20).

A token-bucket limiter keyed by provider id. Collectors call ``context.throttle(provider)``
before each external request; the limiter blocks just long enough to honour that provider's
sustained rate (with a small burst) and tallies the call for usage accounting.

The clock and sleep are injected, so tests exercise the throttling logic deterministically
without real waiting. This is an in-process limiter — correct for a single worker; a
distributed deployment would back the buckets with Redis (a noted follow-up).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

# Conservative defaults for the MVP's public, keyless providers (requests/sec, burst).
DEFAULT_LIMITS: dict[str, tuple[float, int]] = {
    "dns": (20.0, 20),
    "crt.sh": (1.0, 2),      # crt.sh is easily overwhelmed — be gentle
    "rdap": (5.0, 5),
    "wayback": (2.0, 4),
}
_FALLBACK_LIMIT = (5.0, 5)


@dataclass
class _Bucket:
    rate: float
    capacity: int
    tokens: float
    updated: float


class RateLimiter:
    """Thread-safe token-bucket limiter with per-provider usage counts."""

    def __init__(
        self,
        limits: dict[str, tuple[float, int]] | None = None,
        *,
        fallback: tuple[float, int] = _FALLBACK_LIMIT,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._limits = limits if limits is not None else DEFAULT_LIMITS
        self._fallback = fallback
        self._monotonic = monotonic
        self._sleep = sleep
        self._buckets: dict[str, _Bucket] = {}
        self._usage: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def _bucket(self, provider: str) -> _Bucket:
        b = self._buckets.get(provider)
        if b is None:
            rate, capacity = self._limits.get(provider, self._fallback)
            b = _Bucket(rate=rate, capacity=capacity, tokens=float(capacity),
                        updated=self._monotonic())
            self._buckets[provider] = b
        return b

    def acquire(self, provider: str) -> float:
        """Consume one token for `provider`, waiting if the bucket is empty. Returns the
        number of seconds waited (0.0 if a token was immediately available)."""
        with self._lock:
            b = self._bucket(provider)
            now = self._monotonic()
            # refill
            b.tokens = min(b.capacity, b.tokens + (now - b.updated) * b.rate)
            b.updated = now

            waited = 0.0
            if b.tokens < 1.0:
                waited = (1.0 - b.tokens) / b.rate if b.rate > 0 else 0.0
                self._sleep(waited)
                b.updated = self._monotonic()
                b.tokens = 0.0  # the refill over `waited` funds exactly this call
            else:
                b.tokens -= 1.0

            self._usage[provider] += 1
            return waited

    def usage(self) -> dict[str, int]:
        """A snapshot of per-provider call counts."""
        with self._lock:
            return dict(self._usage)


class NullRateLimiter:
    """No-op limiter (used when rate limiting is disabled) that still counts usage."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def acquire(self, provider: str) -> float:
        with self._lock:
            self._usage[provider] += 1
        return 0.0

    def usage(self) -> dict[str, int]:
        with self._lock:
            return dict(self._usage)
