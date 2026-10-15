"""Interpretable, incomplete-observation risk heuristics — NOT fraud probabilities."""
from __future__ import annotations
from dataclasses import dataclass
from .market import TokenSnapshot
from .security import is_flagged


@dataclass(frozen=True)
class RiskReport:
    score: int
    level: str
    findings: tuple[str, ...]
    coverage: str
    checked_count: int
    possible_count: int


def assess(snapshot: TokenSnapshot, security: dict | None = None, previous_liquidity: float | None = None) -> RiskReport:
    score = 0
    findings: list[str] = []
    checked = 0
    total = 5  # Liquidity, daily change, transaction imbalance, liquidity trend, contract security

    if snapshot.liquidity_usd is not None:
        checked += 1
        if snapshot.liquidity_usd < 10_000:
            score += 30
            findings.append("Low pool liquidity (< $10,000); larger trades may move the market substantially.")
        elif snapshot.liquidity_usd < 50_000:
            score += 15
            findings.append("Limited pool liquidity (< $50,000).")

    if snapshot.change_h24_pct is not None:
        checked += 1
        if snapshot.change_h24_pct <= -70:
            score += 20
            findings.append("Token price fell at least 70% over 24 hours; not by itself evidence of a rug pull.")
        elif snapshot.change_h24_pct <= -40:
            score += 10
            findings.append("Token price fell at least 40% over 24 hours.")

    if snapshot.buys_h24 is not None and snapshot.sells_h24 is not None:
        checked += 1
        if snapshot.sells_h24 >= max(30, snapshot.buys_h24 * 3):
            score += 10
            findings.append("24-hour sell transaction count is much higher than buy count (counts, not volume).")

    if previous_liquidity is not None and previous_liquidity > 0 and snapshot.liquidity_usd is not None:
        checked += 1
        liquidity_drop = (previous_liquidity - snapshot.liquidity_usd) / previous_liquidity
        if liquidity_drop >= 0.40:
            score += 35
            findings.append(f"Observed liquidity drop of {liquidity_drop:.0%} since the prior saved scan.")
        elif liquidity_drop >= 0.20:
            score += 20
            findings.append(f"Observed liquidity drop of {liquidity_drop:.0%} since the prior saved scan.")

    if security is not None:
        checked += 1
        security_signals = [
            ("is_honeypot", 45, "GoPlus flags possible honeypot behavior."),
            ("is_mintable", 15, "GoPlus reports minting capability."),
            ("hidden_owner", 15, "GoPlus reports a hidden owner."),
            ("owner_change_balance", 25, "GoPlus reports an owner balance-changing capability."),
            ("is_blacklisted", 10, "GoPlus reports blacklist functionality."),
        ]
        for key, weight, label in security_signals:
            if is_flagged(security.get(key)):
                score += weight
                findings.append(label)

    score = min(100, score)
    if checked < 2:
        level = "Insufficient data"
    elif score >= 75:
        level = "Critical observed risk"
    elif score >= 50:
        level = "High observed risk"
    elif score >= 25:
        level = "Moderate observed risk"
    else:
        level = "Low observed risk (not verified safe)"

    if not findings:
        findings.append("No configured warning threshold was triggered in the available observations; this does not establish safety.")
    if security is None:
        findings.append("Smart-contract security was not assessed; contract risks remain unknown.")
    if checked < total:
        findings.append(f"Only {checked} of {total} signal categories have data. Missing data is not a safety indicator.")
    return RiskReport(score, level, tuple(findings), f"{checked}/{total} categories", checked, total)
