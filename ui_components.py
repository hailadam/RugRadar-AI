"""Presentation-only, escaped HTML for the token research dashboard."""
from __future__ import annotations

from html import escape

import altair as alt

from rugradar.scoring import RiskReport


_ICON_PATHS = {
    "shield": '<path d="M12 3 4 6v6c0 4.5 8 9 8 9s8-4.5 8-9V6z"/><path d="m8.5 12 2.2 2.2 4.8-4.8"/>',
    "liquidity": '<path d="M12 3c-2.2 3.4-6.5 7.5-6.5 11a6.5 6.5 0 0 0 13 0c0-3.5-4.3-7.6-6.5-11Z"/><path d="M9 15a3 3 0 0 0 3 3"/>',
    "volume": '<path d="M4 20h16M7 16V9m5 7V4m5 12v-5"/>',
    "price": '<circle cx="12" cy="12" r="9"/><path d="M15 8.5h-4.5a2 2 0 0 0 0 4h3a2 2 0 0 1 0 4H9M12 6v12"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "history": '<path d="M3 11a9 9 0 1 1 2.5 7M3 5v6h6"/><path d="M12 7v5l3 2"/>',
    "arrow": '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
}


def icon(name: str) -> str:
    """Return a decorative SVG from the fixed icon vocabulary."""
    paths = _ICON_PATHS[name]
    return ('<svg class="ui-icon" xmlns="http://www.w3.org/2000/svg" '
            'width="20" height="20" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true" focusable="false">'
            f'{paths}</svg>')


def _severity(report: RiskReport, score: int) -> tuple[str, str]:
    if score == 0:
        return ("low", "Low") if report.is_complete else ("incomplete", "Incomplete")
    # The backend can assign High to a 45-point honeypot observation.
    # Its severity, rather than a second set of UI thresholds, is authoritative.
    for key in ("critical", "high", "moderate", "low"):
        if report.level.casefold().startswith(key):
            return key, key.capitalize()
    return "incomplete", "Incomplete"


def risk_summary(report: RiskReport) -> str:
    """Render observed warning points without presenting unknowns as safe."""
    score = max(0, min(100, int(report.score)))
    severity, badge = _severity(report, score)
    unknown_zero = score == 0 and not report.is_complete
    headline = ("More evidence is needed." if unknown_zero else
                "No configured warnings found." if score == 0 else
                {"low": "A few warning signals surfaced.",
                 "moderate": "Some warnings deserve a closer look.",
                 "high": "Significant warnings need attention.",
                 "critical": "Strong warning signals surfaced."}.get(severity, "Review the available evidence."))
    value = "Incomplete" if unknown_zero else str(score)
    total = "DATA LIMITED" if unknown_zero else "/100"
    accessible = ("Assessment incomplete; warning score is unknown."
                  if unknown_zero else f"Observed warning score {score}/100. {badge} observed risk.")
    incomplete = ('<p class="risk-limit">Assessment incomplete. Missing data remains unknown.</p>'
                  if not report.is_complete else '')
    return f'''<div class="risk-summary risk-{severity}">
        <svg class="risk-ring" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"
             role="img" aria-label="{escape(accessible, quote=True)}">
            <circle class="gauge-track" cx="100" cy="100" r="78" pathLength="100"
                    fill="none" stroke="var(--risk-track, #e4eef4)" stroke-width="12"/>
            <circle class="gauge-fill" cx="100" cy="100" r="78" pathLength="100"
                    fill="none" stroke="var(--risk-color, #244c67)" stroke-width="12"
                    stroke-linecap="round" stroke-dasharray="{score} 100"
                    transform="rotate(-90 100 100)" opacity="{0 if unknown_zero else 1}"/>
            <text class="gauge-value" x="100" y="99" text-anchor="middle">{value}</text>
            <text class="gauge-total" x="100" y="122" text-anchor="middle">{total}</text>
        </svg>
        <div class="risk-copy">
            <span class="risk-badge" title="{escape(report.level, quote=True)}">{badge}</span>
            <h3>{headline}</h3>
            <p class="risk-score-label">Observed warning score</p>
            <p class="risk-method">Heuristic warning points, not a fraud probability</p>
            <span class="coverage-chip">{escape(report.coverage)}</span>
            {incomplete}
            <p class="risk-caution">A low score does not certify safety.</p>
        </div>
    </div>'''.replace("\n", "")


_EXPLANATIONS = (
    ("Low pool liquidity", "A smaller pool can make purchases and sales move the price more sharply. This is a liquidity warning, not proof of fraud."),
    ("Limited pool liquidity", "The selected pool has limited trading depth. Larger trades may face price changes and slippage."),
    ("Token price fell at least", "A large recent price decline can signal volatility or selling pressure. A price fall alone does not prove a rug pull."),
    ("24-hour sell transaction count", "The pool recorded many more sell transactions than buys. These are transaction counts, not the total value traded."),
    ("Observed liquidity drop", "The selected pool has less liquidity than in the prior saved scan. This comparison does not reconstruct earlier on-chain withdrawals."),
    ("GoPlus flags possible honeypot behavior.", "The security provider reports possible restrictions on selling. This is a provider warning and should be investigated; the app does not simulate a sale."),
    ("GoPlus reports minting capability.", "Additional tokens may be created. Review who controls this permission and how it could affect supply; minting capability alone does not establish misconduct."),
    ("GoPlus reports a hidden owner.", "The provider reports that ownership control may be difficult to identify. Understanding who can change the contract needs further investigation."),
    ("GoPlus reports an owner balance-changing capability.", "The provider reports a permission that may let an owner change token balances. Consider who controls that permission and what changes it allows."),
    ("GoPlus reports blacklist functionality.", "The contract may restrict selected addresses. This capability does not mean your address is already blocked or prove malicious use."),
)


def warning_panel(report: RiskReport) -> str:
    """Keep actual warnings, coverage gaps, and neutral observations distinct."""
    parts = ['<section class="warning-panel"><div class="panel-heading">'
             f'{icon("shield")}<h3>What the scan found</h3></div>']
    if any(finding.startswith(prefix) for finding in report.findings for prefix, _ in _EXPLANATIONS):
        parts.append('<p class="panel-intro">Why this token was flagged: '
                     'the observations below triggered warning rules. Each finding includes what it could mean.</p>')
    for finding in report.findings:
        safe_finding = escape(finding)
        explanation = next((text for prefix, text in _EXPLANATIONS if finding.startswith(prefix)), None)
        if explanation is not None:
            parts.append(f'<article class="signal-warning">{icon("shield")}<div>'
                         f'<p class="signal-title">{safe_finding}</p>'
                         f'<p class="signal-explanation">{escape(explanation)}</p></div></article>')
        elif finding.startswith("No configured warning threshold"):
            parts.append(f'<div class="no-warnings"><p>{safe_finding}</p></div>')
        else:
            parts.append(f'<div class="coverage-note"><p>{safe_finding}</p></div>')
    if not report.findings:
        parts.append('<div class="coverage-note"><p>No findings were returned. '
                     'This does not establish safety.</p></div>')
    parts.append('</section>')
    return ''.join(parts)


def scan_history_chart(history: list[dict], key: str, label: str, color: str) -> alt.Chart:
    """Chart saved values as separate paths when an observation is unknown."""
    points = []
    segment = 0
    for row in history:
        value = row.get(key)
        if value is None:
            segment += 1
            continue
        points.append({"captured_at": row["captured_at"], "value": value, "segment": str(segment)})
    return (alt.Chart(alt.Data(values=points))
            .mark_line(color=color, strokeWidth=2, point=True)
            .encode(x=alt.X("captured_at:T", title=None, axis=alt.Axis(format="%b %d", grid=False)),
                    y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False)),
                    detail="segment:N",
                    tooltip=[alt.Tooltip("captured_at:T", title="Saved scan"),
                             alt.Tooltip("value:Q", title=label)])
            .properties(height=175)
            .configure_view(stroke=None)
            .configure_axis(labelFontSize=10, labelColor="#678195", gridColor="#e6eef3", domain=False))
