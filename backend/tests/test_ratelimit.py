"""Per-provider rate limiter + usage accounting (SMPLSGHT-20), deterministic & offline."""

from __future__ import annotations

from app.services.ratelimit import NullRateLimiter, RateLimiter
from collectors.base import CollectionContext


class _Clock:
    """A controllable monotonic clock; sleeping advances it (so no real waiting)."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def _limiter(clock: _Clock, limits=None) -> RateLimiter:
    return RateLimiter(limits=limits, monotonic=clock.monotonic, sleep=clock.sleep)


def test_burst_passes_without_waiting_then_throttles():
    clock = _Clock()
    rl = _limiter(clock, limits={"p": (1.0, 3)})  # 1 rps, burst 3
    # first 3 calls consume the burst with no wait
    assert [rl.acquire("p") for _ in range(3)] == [0.0, 0.0, 0.0]
    # the 4th must wait ~1 token / 1 rps = 1.0s
    waited = rl.acquire("p")
    assert waited == 1.0
    assert clock.slept == [1.0]


def test_tokens_refill_over_time():
    clock = _Clock()
    rl = _limiter(clock, limits={"p": (2.0, 2)})  # 2 rps, burst 2
    rl.acquire("p")
    rl.acquire("p")          # bucket now empty
    clock.t += 1.0           # 1s elapses -> +2 tokens available
    assert rl.acquire("p") == 0.0  # immediate, no wait
    assert rl.acquire("p") == 0.0


def test_providers_are_independent():
    clock = _Clock()
    rl = _limiter(clock, limits={"a": (1.0, 1), "b": (1.0, 1)})
    assert rl.acquire("a") == 0.0
    assert rl.acquire("b") == 0.0  # b's bucket untouched by a
    assert rl.acquire("a") == 1.0  # a now throttles


def test_unknown_provider_uses_fallback():
    clock = _Clock()
    rl = RateLimiter(limits={}, fallback=(10.0, 1),
                     monotonic=clock.monotonic, sleep=clock.sleep)
    assert rl.acquire("mystery") == 0.0
    assert rl.acquire("mystery") == 0.1  # 1 token / 10 rps


def test_usage_accounting_counts_every_call():
    clock = _Clock()
    rl = _limiter(clock, limits={"p": (100.0, 100), "q": (100.0, 100)})
    for _ in range(5):
        rl.acquire("p")
    rl.acquire("q")
    assert rl.usage() == {"p": 5, "q": 1}


def test_context_throttle_uses_limiter_and_is_noop_without_one():
    clock = _Clock()
    rl = _limiter(clock, limits={"dns": (100.0, 100)})
    ctx = CollectionContext(target="example.com", rate_limiter=rl)
    ctx.throttle("dns")
    ctx.throttle("dns")
    assert rl.usage() == {"dns": 2}

    # no limiter attached -> throttle is a harmless no-op
    CollectionContext(target="example.com").throttle("dns")


def test_null_limiter_still_accounts():
    rl = NullRateLimiter()
    assert rl.acquire("p") == 0.0
    rl.acquire("p")
    assert rl.usage() == {"p": 2}


def test_pipeline_reports_provider_usage():
    from app.services.pipeline import run_investigation
    from collectors.base import (
        Collector,
        CollectorOutcome,
        CollectorResult,
        CollectorRun,
        Provenance,
    )

    class _Throttler(Collector):
        name = "throttler"

        def collect(self, context: CollectionContext) -> CollectorRun:
            context.throttle("dns")
            context.throttle("dns")
            context.throttle("crt.sh")
            return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[
                CollectorResult(asset_type="domain", value="example.com",
                                provenance=Provenance.now(source="x", confidence=0.9))])

    res = run_investigation("example.com", collectors=[_Throttler()],
                            rate_limiter=NullRateLimiter())
    assert res.provider_usage == {"dns": 2, "crt.sh": 1}
