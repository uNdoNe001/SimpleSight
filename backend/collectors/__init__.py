"""OSINT collectors.

All collectors are passive in the MVP and implement the `Collector` interface
defined in `collectors.base`.
"""

from collectors.base import Collector, CollectorResult, Provenance

__all__ = ["Collector", "CollectorResult", "Provenance"]
