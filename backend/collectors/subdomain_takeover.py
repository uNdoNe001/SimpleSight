"""Subdomain-takeover detection (Phase 2 · Story C).

A *dependent* collector: it runs in a second pipeline stage once subdomains have been
discovered, receiving them via `context.scope["subdomains"]`. For each subdomain it resolves
the CNAME and checks the target against a fingerprint set of services that are prone to
dangling-record takeover (a CNAME pointing at an unclaimed third-party resource).

Strictly passive: it only performs ordinary DNS resolution (CNAME, then an A lookup of the
CNAME target to see whether the target still resolves). It never issues HTTP requests or
otherwise probes the third-party service, so it cannot *confirm* an exploitable takeover —
it surfaces candidates, and the findings engine grades them (unresolved target = stronger
signal) while keeping them clearly caveated.
"""

from __future__ import annotations

import dns.resolver

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)

#: service name -> CNAME-target suffixes that indicate delegation to that service.
TAKEOVER_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "GitHub Pages": (".github.io",),
    "AWS S3": (".s3.amazonaws.com", ".s3-website"),
    "Heroku": (".herokuapp.com", ".herokudns.com"),
    "Azure": (
        ".azurewebsites.net", ".cloudapp.net", ".cloudapp.azure.com",
        ".trafficmanager.net", ".blob.core.windows.net", ".azureedge.net",
    ),
    "Fastly": (".fastly.net",),
    "Shopify": (".myshopify.com",),
    "Zendesk": (".zendesk.com",),
    "Unbounce": (".unbounce.com",),
    "Tumblr": (".domains.tumblr.com",),
    "Pantheon": (".pantheonsite.io",),
    "Read the Docs": (".readthedocs.io",),
    "Surge.sh": (".surge.sh",),
    "Bitbucket": (".bitbucket.io",),
    "Ghost": (".ghost.io",),
    "Netlify": (".netlify.app", ".netlify.com"),
    "Wordpress.com": (".wordpress.com",),
}


def match_service(cname_target: str) -> str | None:
    """Return the service name whose fingerprint the CNAME target matches, else None."""
    t = cname_target.rstrip(".").lower()
    for service, suffixes in TAKEOVER_FINGERPRINTS.items():
        if any(suffix in t for suffix in suffixes):
            return service
    return None


class SubdomainTakeoverCollector(Collector):
    name = "subdomain_takeover"
    description = (
        "Checks discovered subdomains' CNAME targets against dangling-service fingerprints."
    )
    required_keys = ()  # keyless
    passive = True

    def __init__(self, resolver: dns.resolver.Resolver | None = None) -> None:
        self._resolver = resolver or dns.resolver.Resolver()

    def _resolves(self, name: str) -> bool | None:
        """True/False whether `name` has an A record; None if the lookup was inconclusive."""
        try:
            self._resolver.resolve(name, "A")
            return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return False
        except Exception:  # noqa: BLE001 - inconclusive, don't claim dangling
            return None

    def collect(self, context: CollectionContext) -> CollectorRun:
        subdomains = context.scope.get("subdomains", [])
        results: list[CollectorResult] = []
        errors: list[str] = []

        for sub in subdomains:
            context.throttle("dns")
            try:
                answer = self._resolver.resolve(sub, "CNAME")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue  # no CNAME -> not a delegation, nothing to check
            except Exception as exc:  # noqa: BLE001 - contain one lookup's failure
                errors.append(f"{sub}: {type(exc).__name__}")
                continue

            target = answer[0].to_text().rstrip(".").lower()
            service = match_service(target)
            if service is None:
                continue  # delegated, but not to a takeover-prone service

            context.throttle("dns")
            resolves = self._resolves(target)
            dangling = resolves is False  # None (inconclusive) is not treated as dangling
            results.append(CollectorResult(
                asset_type="takeover_candidate",
                value=sub,
                # Unresolved target is a stronger signal -> higher confidence.
                provenance=Provenance.now(source="dns", confidence=0.85 if dangling else 0.6),
                attributes={
                    "subdomain": sub, "cname_target": target, "service": service,
                    "dangling": dangling, "target_resolves": resolves,
                },
            ))

        if subdomains and len(errors) == len(subdomains):
            return CollectorRun(
                outcome=CollectorOutcome.FAILED,
                reason=f"all CNAME lookups failed ({'; '.join(errors)})",
            )
        if errors:
            return CollectorRun(
                outcome=CollectorOutcome.PARTIAL, results=results,
                reason=f"some CNAME lookups failed ({'; '.join(errors)})",
            )
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
