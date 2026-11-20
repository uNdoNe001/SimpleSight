"""Public technology fingerprinting collector (SMPLSGHT-26, OSINT018).

Passive and keyless: infers the technologies an organization uses from public DNS signals
it already publishes — the nameserver and mail providers, SPF includes, and the SaaS
verification TXT records domains add when onboarding a service. It performs only ordinary
DNS resolution (NS, MX, TXT); no active probing of the target's infrastructure.

Every emitted `technology` asset names the concrete record that matched, so the inference is
traceable (SMPLSGHT-21) and never fabricated. Confidence is moderate: these signals are
strong hints, not proof of current use.
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

# (substring, technology, category). Matched case-insensitively against record data.
_NS_SIGNATURES = [
    ("cloudflare", "Cloudflare", "dns/cdn"),
    ("awsdns", "AWS Route 53", "dns"),
    ("azure-dns", "Azure DNS", "dns"),
    ("googledomains.com", "Google Cloud DNS", "dns"),
    ("google.com", "Google Cloud DNS", "dns"),
    ("nsone.net", "NS1", "dns"),
    ("domaincontrol.com", "GoDaddy", "dns/registrar"),
    ("dnsmadeeasy", "DNS Made Easy", "dns"),
    ("akam.net", "Akamai", "dns/cdn"),
]
_MX_SIGNATURES = [
    ("google.com", "Google Workspace", "email"),
    ("googlemail.com", "Google Workspace", "email"),
    ("outlook.com", "Microsoft 365", "email"),
    ("protection.outlook.com", "Microsoft 365", "email"),
    ("pphosted.com", "Proofpoint", "email-security"),
    ("ppe-hosted.com", "Proofpoint", "email-security"),
    ("mimecast.com", "Mimecast", "email-security"),
    ("messagelabs.com", "Broadcom Email Security", "email-security"),
    ("mailgun", "Mailgun", "email"),
    ("zoho", "Zoho Mail", "email"),
]
# TXT signatures: substring in the record -> technology. Covers SPF includes and the
# verification tokens services ask domains to publish.
_TXT_SIGNATURES = [
    ("include:_spf.google.com", "Google Workspace", "email"),
    ("include:spf.protection.outlook.com", "Microsoft 365", "email"),
    ("include:amazonses.com", "Amazon SES", "email"),
    ("include:mailgun.org", "Mailgun", "email"),
    ("include:sendgrid.net", "SendGrid", "email"),
    ("include:_spf.salesforce.com", "Salesforce", "crm"),
    ("include:servers.mcsv.net", "Mailchimp", "marketing"),
    ("google-site-verification", "Google (Search Console/Workspace)", "verification"),
    ("facebook-domain-verification", "Meta / Facebook", "verification"),
    ("atlassian-domain-verification", "Atlassian", "saas"),
    ("docusign", "DocuSign", "saas"),
    ("adobe-idp-site-verification", "Adobe", "saas"),
    ("stripe-verification", "Stripe", "payments"),
    ("zoom", "Zoom", "saas"),
    ("miro-verification", "Miro", "saas"),
    ("dropbox-domain-verification", "Dropbox", "saas"),
    ("notion", "Notion", "saas"),
    ("ms=", "Microsoft 365", "verification"),
]


class TechnologyFingerprintCollector(Collector):
    name = "tech_fingerprint"
    description = "Infers technologies in use from public DNS signals (NS, MX, SPF, TXT)."
    required_keys = ()  # DNS only, keyless
    passive = True

    def __init__(self, resolver: dns.resolver.Resolver | None = None) -> None:
        self._resolver = resolver or dns.resolver.Resolver()

    def _lookup(self, target: str, rtype: str) -> list[str]:
        try:
            answer = self._resolver.resolve(target, rtype)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
            return []
        except Exception:  # noqa: BLE001 - one record type failing is not fatal
            return []
        return [item.to_text() for item in answer]

    def collect(self, context: CollectionContext) -> CollectorRun:
        target = context.target.strip().lower().rstrip(".")
        results: list[CollectorResult] = []
        seen: set[str] = set()  # dedupe (technology, matched-record) within this run

        def emit(tech: str, category: str, record: str, rtype: str) -> None:
            key = f"{tech}|{record}"
            if key in seen:
                return
            seen.add(key)
            results.append(CollectorResult(
                asset_type="technology",
                value=tech,
                provenance=Provenance.now(source="dns-fingerprint", confidence=0.8),
                attributes={"category": category, "evidence_record": record,
                            "record_type": rtype, "domain": target},
            ))

        context.throttle("dns")
        for ns in self._lookup(target, "NS"):
            low = ns.lower()
            for sub, tech, cat in _NS_SIGNATURES:
                if sub in low:
                    emit(tech, cat, ns.rstrip("."), "NS")

        context.throttle("dns")
        for mx in self._lookup(target, "MX"):
            low = mx.lower()
            for sub, tech, cat in _MX_SIGNATURES:
                if sub in low:
                    emit(tech, cat, mx.rstrip("."), "MX")

        context.throttle("dns")
        for txt in self._lookup(target, "TXT"):
            low = txt.lower()
            for sub, tech, cat in _TXT_SIGNATURES:
                if sub in low:
                    emit(tech, cat, txt.strip('"'), "TXT")

        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=results)
