"""Per-provider rate limiting and usage accounting (SMPLSGHT-20).

A token-bucket limiter keyed by provider id. Collectors call ``context.throttle(provider)``
before each external request; the limiter blocks just long enough to honour that provider's
sustained rate (with a small burst) and tallies the call for usage accounting.

The clock and sleep are injected, so tests exercise the throttling logic deterministically
without real waiting. ``RateLimiter`` is in-process (correct for a single worker);
``RedisRateLimiter`` (SMPLSGHT-60) backs the same token-bucket with Redis so limits hold across
worker processes. ``build_rate_limiter`` picks the backend from settings; the in-memory limiter
stays the default and the test path.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


# Atomic token-bucket in Lua: refill by elapsed time, consume one token (or compute the wait),
# and tally usage — all in a single round trip so concurrent workers can't race. KEYS[1] is the
# provider's bucket hash, KEYS[2] the shared usage hash; ARGV = now, rate, capacity, provider.
# A Python port of this exact logic lives in the test's fake Redis and must stay in sync.
_LUA_TOKEN_BUCKET = """
local d = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(d[1])
local updated = tonumber(d[2])
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cap = tonumber(ARGV[3])
if tokens == nil then tokens = cap; updated = now end
tokens = math.min(cap, tokens + (now - updated) * rate)
local waited = 0
if tokens < 1 then
  if rate > 0 then waited = (1 - tokens) / rate end
  updated = now + waited
  tokens = 0
else
  tokens = tokens - 1
  updated = now
end
redis.call('HMSET', KEYS[1], 'tokens', tokens, 'updated', updated)
redis.call('HINCRBY', KEYS[2], ARGV[4], 1)
return tostring(waited)
"""


class RedisRateLimiter:
    """Distributed token-bucket limiter (SMPLSGHT-60), sharing state across workers via Redis.

    Same interface as ``RateLimiter`` (``acquire``/``usage``). The clock defaults to wall time so
    all workers agree (monotonic clocks are per-process); clock and sleep are injectable for
    deterministic tests. The refill/consume step is atomic (one Lua eval), so two workers hitting
    the same provider cannot both consume the last token.
    """

    def __init__(
        self,
        redis_client: Any,
        limits: dict[str, tuple[float, int]] | None = None,
        *,
        fallback: tuple[float, int] = _FALLBACK_LIMIT,
        prefix: str = "simplesight:rl",
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._redis = redis_client
        self._limits = limits if limits is not None else DEFAULT_LIMITS
        self._fallback = fallback
        self._prefix = prefix
        self._usage_key = f"{prefix}:usage"
        self._clock = clock
        self._sleep = sleep

    def acquire(self, provider: str) -> float:
        rate, capacity = self._limits.get(provider, self._fallback)
        bucket_key = f"{self._prefix}:bucket:{provider}"
        raw = self._redis.eval(
            _LUA_TOKEN_BUCKET, 2, bucket_key, self._usage_key,
            self._clock(), rate, capacity, provider,
        )
        waited = float(raw.decode() if isinstance(raw, bytes) else raw)
        if waited > 0:
            self._sleep(waited)
        return waited

    def usage(self) -> dict[str, int]:
        raw = self._redis.hgetall(self._usage_key) or {}
        out: dict[str, int] = {}
        for k, v in raw.items():
            key = k.decode() if isinstance(k, bytes) else k
            out[key] = int(v)
        return out


def build_rate_limiter(redis_factory: Callable[[], Any] | None = None) -> object:
    """Construct the limiter configured in settings.

    Returns a ``NullRateLimiter`` when limiting is disabled, a ``RedisRateLimiter`` when the
    backend is "redis" (sharing limits across workers), else the in-process ``RateLimiter``.
    """
    from app.core.config import settings

    if not settings.rate_limit_enabled:
        return NullRateLimiter()
    if settings.rate_limit_backend == "redis":
        if redis_factory is None:
            from app.queue import get_redis

            redis_factory = get_redis
        return RedisRateLimiter(redis_factory(), prefix=settings.rate_limit_redis_prefix)
    return RateLimiter()


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
