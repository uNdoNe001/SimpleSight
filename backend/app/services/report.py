"""Executive Intelligence Report — server-side PDF generation (SMPLSGHT-39/-40).

`build_report_pdf` is a pure function of a `ReportData` value, so the whole template renders
offline in tests without a database. `gather_report_data` assembles that value from the ORM.

Guardrail (product spec): the report never invents content. It renders only the findings and
counts already derived and stored by the collection run; the executive summary is templated
deterministically from those numbers, not generated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Finding, Investigation, Organization
from app.services.scoring import ExposureScore, compute_exposure

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
# Grade -> accent color for the exposure-score block.
_GRADE_COLORS = {
    "F": colors.HexColor("#991b1b"), "D": colors.HexColor("#dc2626"),
    "C": colors.HexColor("#d97706"), "B": colors.HexColor("#a16207"),
    "A": colors.HexColor("#047857"),
}
_SEVERITY_COLORS = {
    "critical": colors.HexColor("#991b1b"),
    "high": colors.HexColor("#dc2626"),
    "medium": colors.HexColor("#d97706"),
    "low": colors.HexColor("#a16207"),
    "info": colors.HexColor("#0369a1"),
}
_INK = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#64748b")
_RULE = colors.HexColor("#e2e8f0")
_BRAND = colors.HexColor("#2563eb")


@dataclass
class ReportData:
    organization_name: str
    primary_domain: str | None
    assessment_type: str
    status: str
    authorized_by: str | None
    authorization_scope: str | None
    authorized_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    findings: list[dict] = field(default_factory=list)
    asset_counts: dict[str, int] = field(default_factory=dict)
    total_assets: int = 0
    exposure: ExposureScore | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def gather_report_data(db: Session, investigation: Investigation) -> ReportData:
    org = db.get(Organization, investigation.organization_id)
    findings = list(
        db.scalars(
            select(Finding).where(Finding.investigation_id == investigation.id)
        )
    )
    findings_sorted = sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.index(f.severity) if f.severity in SEVERITY_ORDER
                       else 99, -f.confidence, f.title),
    )
    counts = Counter(a.asset_type for a in investigation.assets)
    return ReportData(
        organization_name=org.name if org else "(unknown organization)",
        primary_domain=org.primary_domain if org else None,
        assessment_type=investigation.assessment_type,
        status=investigation.status,
        authorized_by=investigation.authorized_by,
        authorization_scope=investigation.authorization_scope,
        authorized_at=investigation.authorized_at,
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        findings=[
            {
                "title": f.title,
                "severity": f.severity,
                "classification": f.classification,
                "status": f.status,
                "confidence": f.confidence,
                "description": f.description,
                "finding_type": f.finding_type,
                "evidence": f.evidence or [],
            }
            for f in findings_sorted
        ],
        asset_counts=dict(counts),
        total_assets=sum(counts.values()),
        exposure=compute_exposure(findings),
    )


def _fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"


def _summary_narrative(active: list[dict], sev_counts: Counter) -> str:
    """A deterministic, number-driven summary sentence — no invention."""
    if not active:
        return (
            "Passive collection completed and no notable findings were derived from the "
            "observed digital footprint. This is not an assertion of security; it reflects "
            "only what passive sources surfaced."
        )
    parts = [f"{sev_counts[s]} {s}" for s in SEVERITY_ORDER if sev_counts[s]]
    highest = next(s for s in SEVERITY_ORDER if sev_counts[s])
    confirmed = sum(1 for f in active if f["classification"] == "confirmed")
    return (
        f"Passive collection derived {len(active)} active finding(s) "
        f"({', '.join(parts)}); the most severe is rated <b>{highest}</b>. "
        f"{confirmed} of {len(active)} rest on confirmed (authoritative or corroborated) "
        f"evidence; the remainder are unverified passive signals that warrant direct "
        f"validation before action."
    )


def build_report_pdf(data: ReportData) -> bytes:
    """Render the Executive Intelligence Report to PDF bytes (SMPLSGHT-39/-40)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.9 * inch, bottomMargin=0.8 * inch,
        title=f"Executive Intelligence Report — {data.organization_name}",
        author="SimpleSight",
    )

    ss = getSampleStyleSheet()
    h_title = ParagraphStyle("hTitle", parent=ss["Title"], fontSize=22, textColor=_INK,
                             spaceAfter=2, leading=26)
    h_sub = ParagraphStyle("hSub", parent=ss["Normal"], fontSize=11, textColor=_MUTED,
                           spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, textColor=_INK,
                        spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, textColor=_INK,
                          leading=14, alignment=TA_LEFT)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=_MUTED,
                           leading=11)
    f_title = ParagraphStyle("fTitle", parent=body, fontSize=10.5, spaceAfter=2,
                             textColor=_INK)

    story: list = []

    # --- cover / header ---
    story.append(Paragraph("SimpleSight · Summit Cyber Group", h_sub))
    story.append(Paragraph("Executive Intelligence Report", h_title))
    subject = escape(data.organization_name)
    if data.primary_domain:
        subject += f" &nbsp;·&nbsp; <font color='#2563eb'>{escape(data.primary_domain)}</font>"
    story.append(Paragraph(subject, h_sub))
    story.append(Paragraph(f"Generated {_fmt_dt(data.generated_at)}", small))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=_RULE))

    # --- engagement metadata ---
    meta_rows = [
        ["Assessment type", escape(data.assessment_type)],
        ["Collection status", escape(data.status)],
        ["Collection window", f"{_fmt_dt(data.started_at)}  →  {_fmt_dt(data.completed_at)}"],
        ["Assets discovered", str(data.total_assets)],
    ]
    meta = Table([[Paragraph(f"<b>{k}</b>", small), Paragraph(v, small)] for k, v in meta_rows],
                 colWidths=[1.7 * inch, 4.6 * inch])
    meta.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, _RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(Spacer(1, 8))
    story.append(meta)

    # --- authorization attestation (SMPLSGHT-15 — part of the record) ---
    story.append(Paragraph("Authorization", h2))
    if data.authorized_by:
        story.append(Paragraph(
            f"Collection was authorized by <b>{escape(data.authorized_by)}</b> on "
            f"{_fmt_dt(data.authorized_at)}. Attested scope: "
            f"{escape(data.authorization_scope or '—')}.", body))
    else:
        story.append(Paragraph(
            "<b>No authorization attestation is on record for this investigation.</b>", body))

    # --- executive summary ---
    active = [f for f in data.findings if f["status"] != "dismissed"]
    sev_counts = Counter(f["severity"] for f in active)
    story.append(Paragraph("Executive summary", h2))

    # Exposure score (SMPLSGHT-48): a single number summarizing posture.
    exposure = data.exposure or compute_exposure(data.findings)
    grade_color = _GRADE_COLORS.get(exposure.grade, _MUTED)
    score_cell = Paragraph(
        f'<font size="22"><b>{exposure.score}</b></font>'
        f'<font size="10">/100</font><br/>'
        f'<font size="11"><b>Grade {exposure.grade} · {exposure.label}</b></font>',
        ParagraphStyle("score", parent=f_title, textColor=grade_color, leading=24))
    rationale_cell = Paragraph(
        f"<b>Exposure score.</b> {escape(exposure.rationale)} A relative indicator derived "
        f"only from passively observed findings — not an assertion of overall security.",
        small)
    score_table = Table([[score_cell, rationale_cell]], colWidths=[1.6 * inch, 5.0 * inch])
    score_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _RULE),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, _RULE),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f8fafc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph(_summary_narrative(active, sev_counts), body))
    story.append(Spacer(1, 8))

    header = [Paragraph(f"<b>{s.upper()}</b>", small) for s in SEVERITY_ORDER]
    values = [Paragraph(f"<b>{sev_counts.get(s, 0)}</b>", f_title) for s in SEVERITY_ORDER]
    sev_table = Table([header, values], colWidths=[1.25 * inch] * 5)
    style = [
        ("BOX", (0, 0), (-1, -1), 0.5, _RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _RULE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, s in enumerate(SEVERITY_ORDER):
        style.append(("TEXTCOLOR", (i, 0), (i, 0), _SEVERITY_COLORS[s]))
    sev_table.setStyle(TableStyle(style))
    story.append(sev_table)

    # --- key findings ---
    story.append(Paragraph("Key findings", h2))
    if not active:
        story.append(Paragraph("No active findings.", body))
    for f in active:
        sev = f["severity"]
        hexcolor = "#" + _SEVERITY_COLORS[sev].hexval()[2:]  # 0x RRGGBB -> #RRGGBB
        chip = f"<b><font color='{hexcolor}'>[{sev.upper()}]</font></b>"
        story.append(Paragraph(f"{chip} &nbsp;{escape(f['title'])}", f_title))
        story.append(Paragraph(
            f"<font color='#64748b'>{escape(f['classification'])} · "
            f"confidence {f['confidence']:.2f} · {escape(f['finding_type'])} · "
            f"status {escape(f['status'])}</font>", small))
        story.append(Paragraph(escape(f["description"]), body))
        if f["evidence"]:
            ev_lines = []
            for e in f["evidence"][:8]:
                srcs = ", ".join(escape(str(s)) for s in e.get("sources", []))
                ev_lines.append(
                    f"• <b>{escape(str(e.get('asset_type', '')))}</b> "
                    f"{escape(str(e.get('value', '')))} "
                    f"<font color='#64748b'>— {srcs}</font>")
            story.append(Paragraph("<br/>".join(ev_lines), small))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=0.5, color=_RULE))
        story.append(Spacer(1, 4))

    # --- digital footprint ---
    story.append(Paragraph("Digital footprint summary", h2))
    if data.asset_counts:
        rows = [[Paragraph("<b>Asset type</b>", small), Paragraph("<b>Count</b>", small)]]
        for t in sorted(data.asset_counts):
            rows.append([Paragraph(escape(t), small), Paragraph(str(data.asset_counts[t]), small)])
        atable = Table(rows, colWidths=[3.0 * inch, 1.5 * inch])
        atable.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, _RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(atable)
    else:
        story.append(Paragraph("No assets were discovered.", body))

    # --- methodology & limitations ---
    story.append(PageBreak())
    story.append(Paragraph("Methodology &amp; limitations", h2))
    for line in (
        ("Collection was <b>passive only</b>: public DNS, Certificate Transparency logs, "
         "RDAP/WHOIS registration data, and public web archives. No active scanning, probing, "
         "or authentication against the subject's infrastructure was performed."),
        ("Findings are <b>derived deterministically</b> from the collected evidence; the "
         "platform does not fabricate findings. Each finding lists the concrete evidence "
         "behind it."),
        ("Findings marked <b>unverified</b> rest on a single passive signal or an inference "
         "from absence and should be independently validated before action. The presence of "
         "a hostname in a log does not prove it resolves or is reachable."),
        ("This is a <b>point-in-time</b> snapshot of passively observable data and is not an "
         "exhaustive security assessment."),
    ):
        story.append(Paragraph(line, body))
        story.append(Spacer(1, 4))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(0.9 * inch, 0.55 * inch,
                          "SimpleSight — Confidential · For the authorized recipient only")
        canvas.drawRightString(7.6 * inch, 0.55 * inch, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
