"""Derive triageable findings from collected assets (SMPLSGHT-32/-33).

Design constraint from the product spec: *the platform must not invent findings*. So this
is a deterministic rule engine over the already-collected, already-persisted assets — not a
model. Every finding it emits carries an `evidence` envelope listing the concrete asset(s)
that substantiate it, and nothing is emitted without a supporting asset.

`classification` (SMPLSGHT-33) records how much the evidence can be trusted:
  - CONFIRMED  — positive, authoritative, or multi-source evidence (e.g. the registry says
                 the domain is expired; a host corroborated by DNS *and* CT).
  - UNVERIFIED — a single passive signal, or an inference from absence (e.g. a hostname seen
                 only in a certificate, which does not prove it resolves; "no SPF observed").

The engine is a pure function of the asset list so it is trivially testable offline;
persistence (and preserving analyst triage across re-runs) lives in `persist_findings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import (
    Finding,
    FindingClassification,
    FindingSeverity,
    FindingStatus,
    Investigation,
)
from app.schemas import AssetOut

# Leftmost-label keywords that mark a hostname as sensitive / non-production surface.
# High-sensitivity: admin panels, internal tooling, data stores, remote access.
_HIGH_SENSITIVITY = {
    "admin", "vpn", "internal", "intranet", "jenkins", "gitlab", "grafana",
    "kibana", "phpmyadmin", "db", "database", "sql", "backup", "jira", "sonar",
}
# Medium-sensitivity: pre-production and legacy environments.
_MEDIUM_SENSITIVITY = {
    "dev", "development", "staging", "stage", "test", "testing", "qa", "uat",
    "sandbox", "beta", "demo", "old", "legacy", "preprod", "ftp",
}

_SURFACE_SUMMARY_THRESHOLD = 25  # subdomain count above which the surface is "large"


@dataclass
class FindingCandidate:
    """An engine-produced finding, pre-persistence."""

    finding_key: str
    finding_type: str
    title: str
    description: str
    severity: FindingSeverity
    confidence: float
    classification: FindingClassification
    evidence: list[dict] = field(default_factory=list)


def _evidence(asset: AssetOut) -> dict:
    """A compact, serializable pointer back to the asset that substantiates a finding."""
    return {
        "asset_type": asset.asset_type,
        "value": asset.value,
        "confidence": asset.confidence,
        "sources": [s.source for s in asset.sources],
    }


def _is_corroborated(asset: AssetOut) -> bool:
    """An asset counts as corroborated when independent sources agree, or one source is
    highly confident."""
    distinct_sources = {s.source for s in asset.sources}
    return len(distinct_sources) >= 2 or asset.confidence >= 0.9


def _parse_date(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        # date-only form, e.g. "2027-05-13"
        try:
            dt = datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _leftmost_label(host: str) -> str:
    return host.split(".", 1)[0] if host else ""


def _sensitive_hostname_findings(hosts: list[AssetOut]) -> list[FindingCandidate]:
    out: list[FindingCandidate] = []
    for host in hosts:
        label = _leftmost_label(host.value)
        if label in _HIGH_SENSITIVITY:
            severity = FindingSeverity.HIGH
        elif label in _MEDIUM_SENSITIVITY:
            severity = FindingSeverity.MEDIUM
        else:
            continue
        classification = (
            FindingClassification.CONFIRMED
            if _is_corroborated(host)
            else FindingClassification.UNVERIFIED
        )
        note = (
            "Corroborated by multiple sources."
            if classification is FindingClassification.CONFIRMED
            else "Seen in a single passive source; existence in a certificate or log does "
            "not prove the host resolves or is reachable."
        )
        out.append(
            FindingCandidate(
                finding_key=f"sensitive-host:{host.value}",
                finding_type="sensitive_hostname",
                title=f"Sensitive hostname exposed: {host.value}",
                description=(
                    f"The hostname '{host.value}' is publicly discoverable and its name "
                    f"('{label}') suggests a non-production or sensitive service. "
                    f"Publicly enumerable internal/pre-production hosts widen the attack "
                    f"surface. {note}"
                ),
                severity=severity,
                confidence=host.confidence,
                classification=classification,
                evidence=[_evidence(host)],
            )
        )
    return out


def _registration_findings(whois_assets: list[AssetOut]) -> list[FindingCandidate]:
    out: list[FindingCandidate] = []
    now = datetime.now(UTC)
    for asset in whois_assets:
        expiry = _parse_date(asset.attributes.get("expiration_date"))
        if expiry is None:
            continue
        days = (expiry - now).days
        if days < 0:
            severity, title, detail = (
                FindingSeverity.HIGH,
                f"Domain registration expired: {asset.value}",
                (f"The registry expiration date ({expiry.date().isoformat()}) is in the "
                 f"past. An expired domain can lapse and be re-registered by a third party."),
            )
        elif days <= 30:
            severity, title, detail = (
                FindingSeverity.HIGH,
                f"Domain registration expiring soon: {asset.value}",
                (f"The registration expires in {days} day(s) "
                 f"({expiry.date().isoformat()}). Lapsing risks loss of the domain."),
            )
        elif days <= 60:
            severity, title, detail = (
                FindingSeverity.MEDIUM,
                f"Domain registration expiring: {asset.value}",
                (f"The registration expires in {days} day(s) "
                 f"({expiry.date().isoformat()}). Plan renewal."),
            )
        else:
            continue
        out.append(
            FindingCandidate(
                finding_key=f"registration-expiry:{asset.value}",
                finding_type="registration_expiry",
                title=title,
                # Registry/RDAP data is authoritative -> confirmed.
                description=detail,
                severity=severity,
                confidence=asset.confidence,
                classification=FindingClassification.CONFIRMED,
                evidence=[_evidence(asset)],
            )
        )
    return out


def _email_auth_findings(
    target: str, dns_records: list[AssetOut]
) -> list[FindingCandidate]:
    """Flag a mail-handling domain with no observable SPF policy.

    Grounded in positive evidence (MX records were observed) plus an absence (no TXT record
    carried an SPF policy). Because it rests partly on absence, it is classified UNVERIFIED.
    Emitted only when DNS records were actually collected, so a failed lookup never
    masquerades as "no SPF".
    """
    if not dns_records:
        return []
    has_mx = any(a.attributes.get("record_type") == "MX" for a in dns_records)
    if not has_mx:
        return []
    txt_values = [
        str(a.attributes.get("data", "")).lower()
        for a in dns_records
        if a.attributes.get("record_type") == "TXT"
    ]
    if any("v=spf1" in v for v in txt_values):
        return []
    mx_evidence = [_evidence(a) for a in dns_records if a.attributes.get("record_type") == "MX"]
    return [
        FindingCandidate(
            finding_key=f"email-auth-spf:{target}",
            finding_type="missing_spf",
            title=f"No SPF record observed for mail-handling domain: {target}",
            description=(
                f"'{target}' publishes MX records (it receives mail) but no TXT record "
                f"with an SPF policy (v=spf1) was observed. Absent SPF, the domain is "
                f"easier to spoof in phishing. Verify directly before acting — this is "
                f"inferred from the absence of a record."
            ),
            severity=FindingSeverity.MEDIUM,
            confidence=0.6,
            classification=FindingClassification.UNVERIFIED,
            evidence=mx_evidence,
        )
    ]


def _dns_hygiene_findings(
    target: str, dns_records: list[AssetOut]
) -> list[FindingCandidate]:
    """Flag missing DNS hardening: no CAA (certificate-issuance restriction) and no DNSSEC.

    Both rest on a direct authoritative lookup returning no such record, so they are
    absence-based and classified UNVERIFIED. Emitted only when DNS resolution actually
    succeeded (records present), so a failed lookup never reads as "missing".
    """
    if not dns_records:
        return []
    types = {a.attributes.get("record_type") for a in dns_records}
    out: list[FindingCandidate] = []

    if "CAA" not in types:
        out.append(FindingCandidate(
            finding_key=f"dns-no-caa:{target}",
            finding_type="missing_caa",
            title=f"No CAA record restricting certificate issuance for {target}",
            description=(
                f"'{target}' publishes no CAA record. CAA lets a domain owner list which "
                f"certificate authorities may issue certificates for it; without one, any "
                f"CA may issue, widening the mis-issuance risk. Inferred from absence — "
                f"verify directly."
            ),
            severity=FindingSeverity.LOW,
            confidence=0.6,
            classification=FindingClassification.UNVERIFIED,
            evidence=[_evidence(dns_records[0])],
        ))

    if "DNSKEY" not in types:
        out.append(FindingCandidate(
            finding_key=f"dns-no-dnssec:{target}",
            finding_type="missing_dnssec",
            title=f"DNSSEC does not appear to be enabled for {target}",
            description=(
                f"No DNSKEY record was observed for '{target}', indicating the zone is "
                f"likely not DNSSEC-signed. Unsigned zones are more exposed to DNS spoofing "
                f"and cache poisoning. Inferred from absence — confirm with the registrar/DNS "
                f"provider before acting."
            ),
            severity=FindingSeverity.LOW,
            confidence=0.6,
            classification=FindingClassification.UNVERIFIED,
            evidence=[_evidence(dns_records[0])],
        ))
    return out


def _email_posture_findings(
    target: str, email_assets: list[AssetOut], dns_records: list[AssetOut]
) -> list[FindingCandidate]:
    """Flag gaps in published email-authentication posture (DMARC, DKIM, MTA-STS).

    Only evaluated for mail-handling domains (MX observed), mirroring the SPF rule. Each
    finding is grounded in the authoritative lookup the email-security collector performed:
      - a *missing* mechanism rests on an absence, so it is UNVERIFIED (verify directly);
      - a *present-but-weak* mechanism (DMARC p=none) rests on the actual record, so it is
        CONFIRMED.
    SPF is handled separately by `_email_auth_findings`.
    """
    if not dns_records or not email_assets:
        return []
    if not any(a.attributes.get("record_type") == "MX" for a in dns_records):
        return []
    mx_evidence = [
        _evidence(a) for a in dns_records if a.attributes.get("record_type") == "MX"
    ][:1]
    by_mech = {a.attributes.get("mechanism"): a for a in email_assets}
    out: list[FindingCandidate] = []

    dmarc = by_mech.get("dmarc")
    if dmarc is not None:
        if not dmarc.attributes.get("present"):
            out.append(FindingCandidate(
                finding_key=f"email-dmarc-missing:{target}",
                finding_type="missing_dmarc",
                title=f"No DMARC policy published for mail-handling domain: {target}",
                description=(
                    f"'{target}' receives mail (MX present) but no DMARC record was found "
                    f"at _dmarc.{target}. Without DMARC, receivers cannot tell the domain "
                    f"owner how to handle spoofed mail, easing impersonation and phishing. "
                    f"Inferred from the absence of a record — verify directly."
                ),
                severity=FindingSeverity.MEDIUM,
                confidence=0.6,
                classification=FindingClassification.UNVERIFIED,
                evidence=[_evidence(dmarc), *mx_evidence],
            ))
        else:
            policy = (dmarc.attributes.get("policy") or "").lower()
            if policy in ("", "none"):
                out.append(FindingCandidate(
                    finding_key=f"email-dmarc-weak:{target}",
                    finding_type="weak_dmarc",
                    title=f"DMARC is monitor-only (p=none) for {target}",
                    description=(
                        f"'{target}' publishes DMARC but with policy 'p=none', which only "
                        f"reports on spoofed mail and does not block it. Moving to "
                        f"'quarantine' or 'reject' (after monitoring) enforces protection."
                    ),
                    severity=FindingSeverity.LOW,
                    confidence=dmarc.confidence,
                    classification=FindingClassification.CONFIRMED,
                    evidence=[_evidence(dmarc)],
                ))

    mta = by_mech.get("mta_sts")
    if mta is not None and not mta.attributes.get("present"):
        out.append(FindingCandidate(
            finding_key=f"email-mta-sts-missing:{target}",
            finding_type="missing_mta_sts",
            title=f"No MTA-STS policy published for {target}",
            description=(
                f"'{target}' receives mail but publishes no MTA-STS policy "
                f"(_mta-sts.{target}). MTA-STS lets sending servers require TLS for "
                f"inbound mail, reducing downgrade/interception risk. Inferred from "
                f"absence — verify directly."
            ),
            severity=FindingSeverity.LOW,
            confidence=0.6,
            classification=FindingClassification.UNVERIFIED,
            evidence=[_evidence(mta), *mx_evidence],
        ))

    dkim = by_mech.get("dkim")
    if dkim is not None and not dkim.attributes.get("present"):
        probed = dkim.attributes.get("selectors_probed", [])
        out.append(FindingCandidate(
            finding_key=f"email-dkim-none-observed:{target}",
            finding_type="no_dkim_observed",
            title=f"No DKIM selector observed for {target}",
            description=(
                f"None of {len(probed)} common DKIM selectors resolved for '{target}'. "
                f"DKIM selectors are arbitrary, so this does not prove DKIM is unused — it "
                f"only means no common selector was found. Confirm the domain's actual "
                f"selector before acting."
            ),
            severity=FindingSeverity.INFO,
            confidence=0.4,
            classification=FindingClassification.UNVERIFIED,
            evidence=[_evidence(dkim)],
        ))
    return out


def _surface_summary_finding(
    target: str, subdomains: list[AssetOut]
) -> list[FindingCandidate]:
    count = len(subdomains)
    if count == 0:
        return []
    severity = FindingSeverity.LOW if count >= _SURFACE_SUMMARY_THRESHOLD else FindingSeverity.INFO
    sample = sorted(a.value for a in subdomains)[:10]
    return [
        FindingCandidate(
            finding_key=f"surface-summary:{target}",
            finding_type="attack_surface_summary",
            title=f"{count} subdomain(s) discovered for {target}",
            description=(
                f"Passive discovery surfaced {count} distinct subdomain(s) under "
                f"'{target}'. Each is externally visible and part of the attack surface. "
                + (f"Examples: {', '.join(sample)}." if sample else "")
            ),
            severity=severity,
            confidence=0.99,
            classification=FindingClassification.CONFIRMED,
            evidence=[_evidence(a) for a in subdomains[:10]],
        )
    ]


def derive_findings(target: str, assets: list[AssetOut]) -> list[FindingCandidate]:
    """Run every rule over the asset list and return the findings, most severe first."""
    hosts = [a for a in assets if a.asset_type in {"subdomain", "domain"}]
    subdomains = [a for a in assets if a.asset_type == "subdomain"]
    whois_assets = [a for a in assets if a.asset_type == "whois"]
    dns_records = [a for a in assets if a.asset_type == "dns_record"]
    email_assets = [a for a in assets if a.asset_type == "email_security"]

    candidates: list[FindingCandidate] = []
    candidates += _sensitive_hostname_findings(hosts)
    candidates += _registration_findings(whois_assets)
    candidates += _email_auth_findings(target, dns_records)
    candidates += _email_posture_findings(target, email_assets, dns_records)
    candidates += _dns_hygiene_findings(target, dns_records)
    candidates += _surface_summary_finding(target, subdomains)

    order = {s: i for i, s in enumerate(
        [FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM,
         FindingSeverity.LOW, FindingSeverity.INFO]
    )}
    candidates.sort(key=lambda c: (order[c.severity], -c.confidence, c.title))
    return candidates


def persist_findings(
    db: Session, investigation: Investigation, candidates: list[FindingCandidate]
) -> list[Finding]:
    """Replace the investigation's findings with a fresh snapshot, carrying analyst triage
    (`status`) forward for any finding whose stable `finding_key` reappears."""
    prior_status = {f.finding_key: f.status for f in investigation.findings}
    investigation.findings.clear()
    db.flush()

    rows: list[Finding] = []
    for c in candidates:
        row = Finding(
            tenant_id=investigation.tenant_id,
            organization_id=investigation.organization_id,
            finding_key=c.finding_key,
            finding_type=c.finding_type,
            title=c.title,
            description=c.description,
            severity=c.severity.value,
            confidence=c.confidence,
            classification=c.classification.value,
            status=prior_status.get(c.finding_key, FindingStatus.OPEN.value),
            evidence=c.evidence,
        )
        investigation.findings.append(row)
        rows.append(row)
    return rows
