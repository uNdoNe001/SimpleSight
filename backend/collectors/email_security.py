"""Email-security posture collector (Phase 2 · Story A).

Passive: resolves the special DNS names where email-authentication policies are published
and reports which mechanisms a domain has in place. It does **not** send mail, connect to
mail servers, or touch target infrastructure beyond ordinary DNS resolution.

Mechanisms checked (all via TXT at well-known names):
  - DMARC    at `_dmarc.<domain>`                 (v=DMARC1; p=...)
  - MTA-STS  at `_mta-sts.<domain>`               (v=STSv1)
  - BIMI     at `default._bimi.<domain>`          (v=BIMI1) — informational only
  - DKIM     at `<selector>._domainkey.<domain>`  (v=DKIM1) for a set of common selectors

SPF is already observed by the DNS-records collector (apex TXT) and handled in the findings
engine, so it is intentionally not re-checked here.

A clean NoAnswer/NXDOMAIN for a name is treated as an *authoritative absence* (the policy is
not published), not an error. Only resolution failures (timeout, SERVFAIL, …) count as
errors for outcome roll-up.
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

#: Common DKIM selectors published by major mail/ESP providers. DKIM selectors are
#: arbitrary, so this can only *find* DKIM, never prove its absence — the finding engine
#: treats "no selector found" as unverified, low-severity information.
DKIM_SELECTORS = (
    "default", "google", "selector1", "selector2", "k1", "s1", "s2",
    "mail", "dkim", "mandrill", "mxvault", "pm", "zoho",
)


class EmailSecurityCollector(Collector):
    name = "email_security"
    description = (
        "Checks published email-authentication posture (DMARC, DKIM, MTA-STS, BIMI)."
    )
    required_keys = ()  # keyless
    passive = True

    def __init__(
        self,
        resolver: dns.resolver.Resolver | None = None,
        selectors: tuple[str, ...] = DKIM_SELECTORS,
    ) -> None:
        self._resolver = resolver or dns.resolver.Resolver()
        self._selectors = tuple(selectors)

    # -- low-level TXT lookup ------------------------------------------------------------
    def _txt(self, context: CollectionContext, name: str) -> tuple[list[str] | None, str | None]:
        """Return (records, error). records=[] means authoritative absence; records=None
        means the lookup errored (error is a short label)."""
        context.throttle("dns")
        try:
            answer = self._resolver.resolve(name, "TXT")
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return [], None
        except Exception as exc:  # noqa: BLE001 - contain one lookup's failure
            return None, f"{name}: {type(exc).__name__}"
        records = [item.to_text().replace('"', "").strip() for item in answer]
        return records, None

    @staticmethod
    def _first_matching(records: list[str], marker: str) -> str | None:
        marker = marker.lower()
        for rec in records:
            if rec.lower().startswith(marker) or marker in rec.lower():
                return rec
        return None

    @staticmethod
    def _dmarc_policy(record: str) -> str | None:
        for part in record.split(";"):
            part = part.strip()
            if part.lower().startswith("p="):
                return part.split("=", 1)[1].strip().lower()
        return None

    # -- orchestration -------------------------------------------------------------------
    def collect(self, context: CollectionContext) -> CollectorRun:
        target = context.target
        results: list[CollectorResult] = []
        errors: list[str] = []
        determined = 0

        def prov() -> Provenance:
            # Direct, authoritative DNS query -> high confidence.
            return Provenance.now(source="dns", confidence=0.9)

        # --- DMARC ---
        records, err = self._txt(context, f"_dmarc.{target}")
        if err is not None:
            errors.append(err)
        else:
            determined += 1
            record = self._first_matching(records, "v=dmarc1")
            present = record is not None
            results.append(CollectorResult(
                asset_type="email_security",
                value="dmarc",
                provenance=prov(),
                attributes={
                    "mechanism": "dmarc", "present": present,
                    "policy": self._dmarc_policy(record) if record else None,
                    "record": record, "domain": target,
                },
            ))

        # --- MTA-STS ---
        records, err = self._txt(context, f"_mta-sts.{target}")
        if err is not None:
            errors.append(err)
        else:
            determined += 1
            record = self._first_matching(records, "v=stsv1")
            results.append(CollectorResult(
                asset_type="email_security",
                value="mta_sts",
                provenance=prov(),
                attributes={
                    "mechanism": "mta_sts", "present": record is not None,
                    "record": record, "domain": target,
                },
            ))

        # --- BIMI (informational) ---
        records, err = self._txt(context, f"default._bimi.{target}")
        if err is not None:
            errors.append(err)
        else:
            determined += 1
            record = self._first_matching(records, "v=bimi1")
            results.append(CollectorResult(
                asset_type="email_security",
                value="bimi",
                provenance=prov(),
                attributes={
                    "mechanism": "bimi", "present": record is not None,
                    "record": record, "domain": target,
                },
            ))

        # --- DKIM (probe common selectors) ---
        found_selectors: list[str] = []
        dkim_errors = 0
        for selector in self._selectors:
            recs, err = self._txt(context, f"{selector}._domainkey.{target}")
            if err is not None:
                dkim_errors += 1
                continue
            if self._first_matching(recs, "v=dkim1") or any(
                "k=" in r.lower() or "p=" in r.lower() for r in recs
            ):
                found_selectors.append(selector)
        if dkim_errors == len(self._selectors):
            errors.append(f"dkim: {dkim_errors} selector lookup(s) failed")
        else:
            determined += 1
            results.append(CollectorResult(
                asset_type="email_security",
                value="dkim",
                provenance=prov(),
                attributes={
                    "mechanism": "dkim", "present": bool(found_selectors),
                    "selectors": found_selectors,
                    "selectors_probed": list(self._selectors), "domain": target,
                },
            ))

        if determined == 0:
            return CollectorRun(
                outcome=CollectorOutcome.FAILED,
                reason=f"all email-posture lookups failed ({'; '.join(errors)})",
            )
        if errors:
            return CollectorRun(
                outcome=CollectorOutcome.PARTIAL,
                results=results,
                reason=f"some lookups failed ({'; '.join(errors)})",
            )
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
