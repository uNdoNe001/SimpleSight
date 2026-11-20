"""Discovery-plan generation (SMPLSGHT-16).

Before any collection runs, produce a transparent preview of *what the platform will do*:
the targets in scope and, for each registered collector, whether it will run against them,
whether it is passive, and — if it will be skipped — why (an unconfigured provider key).

This is a pure function of the scope + collector registry + the set of configured key names
(not their values), so it renders identically for a draft investigation and a live run. It
supports the authorization step: an analyst can see the methodology before attesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from collectors.base import Collector


@dataclass
class PlanStep:
    collector: str
    description: str
    passive: bool
    required_keys: list[str]
    enabled: bool
    skip_reason: str | None = None


@dataclass
class DiscoveryPlan:
    target: str | None
    additional_targets: list[str] = field(default_factory=list)
    passive_only: bool = True
    steps: list[PlanStep] = field(default_factory=list)
    enabled_count: int = 0
    skipped_count: int = 0


def build_discovery_plan(
    target: str | None,
    additional_targets: list[str],
    collectors: list[Collector],
    configured_keys: set[str],
) -> DiscoveryPlan:
    steps: list[PlanStep] = []
    for c in collectors:
        missing = [k for k in c.required_keys if k not in configured_keys]
        enabled = not missing
        steps.append(PlanStep(
            collector=c.name,
            description=c.description or "",
            passive=c.passive,
            required_keys=list(c.required_keys),
            enabled=enabled,
            skip_reason=(f"missing provider key(s): {', '.join(missing)}" if missing else None),
        ))
    enabled_count = sum(1 for s in steps if s.enabled)
    return DiscoveryPlan(
        target=target,
        additional_targets=additional_targets,
        passive_only=all(c.passive for c in collectors),
        steps=steps,
        enabled_count=enabled_count,
        skipped_count=len(steps) - enabled_count,
    )
