"""WHOIS / domain registration collector (SMPLSGHT-22).

Uses RDAP (the structured, JSON successor to WHOIS) via rdap.org, which bootstraps to the
authoritative registry server and needs no API key. Passive: a registration lookup only.
"""

from __future__ import annotations

import httpx

from collectors.base import (
    CollectionContext,
    Collector,
    CollectorOutcome,
    CollectorResult,
    CollectorRun,
    Provenance,
)

RDAP_URL = "https://rdap.org/domain/"


def _registrar(entities: list[dict]) -> str | None:
    for ent in entities or []:
        if "registrar" in (ent.get("roles") or []):
            # vcardArray = ["vcard", [["version",...], ["fn", {}, "text", "Registrar Name"], ...]]
            vcard = ent.get("vcardArray")
            if isinstance(vcard, list) and len(vcard) == 2:
                for field in vcard[1]:
                    if isinstance(field, list) and field and field[0] == "fn":
                        return field[3]
    return None


def _events(events: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ev in events or []:
        action, date = ev.get("eventAction"), ev.get("eventDate")
        if action and date:
            out[action] = date
    return out


class WhoisRdapCollector(Collector):
    name = "whois_rdap"
    required_keys = ()  # rdap.org is keyless
    passive = True

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": "SimpleSight"}
        )

    def collect(self, context: CollectionContext) -> CollectorRun:
        domain = context.target.strip().lower().rstrip(".")
        resp = self._client.get(f"{RDAP_URL}{domain}")
        if resp.status_code == 404:
            return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[],
                                reason="no RDAP registration record")
        resp.raise_for_status()
        data = resp.json()

        events = _events(data.get("events", []))
        nameservers = [ns.get("ldhName", "").lower().rstrip(".")
                       for ns in data.get("nameservers", []) if ns.get("ldhName")]

        result = CollectorResult(
            asset_type="whois",
            value=domain,
            provenance=Provenance.now(source="rdap", confidence=0.9),
            attributes={
                "registrar": _registrar(data.get("entities", [])),
                "registration_date": events.get("registration"),
                "expiration_date": events.get("expiration"),
                "last_changed": events.get("last changed"),
                "nameservers": nameservers,
                "statuses": data.get("status", []),
            },
        )
        return CollectorRun(outcome=CollectorOutcome.SUCCESS, results=[result])
