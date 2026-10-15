"""Independent market, security, blockchain, and local-history checks."""
from __future__ import annotations

from dataclasses import dataclass, replace
import sqlite3

from .chain import ChainDetails, inspect_chain
from .history import latest_liquidity, save_scan
from .market import DataSourceError, TokenSnapshot, empty_snapshot, fetch_pairs, snapshot_from_pairs
from .networks import get_network, validate_address
from .scoring import RiskReport, assess
from .security import fetch_security


@dataclass(frozen=True)
class SourceCheck:
    name: str
    status: str
    details: str


@dataclass(frozen=True)
class ScanResult:
    snapshot: TokenSnapshot
    report: RiskReport
    warnings: tuple[str, ...]
    sources: tuple[SourceCheck, ...]
    blockchain: ChainDetails
    history_saved: bool


def analyze_token(address: str, network: str = "base", check_security: bool = True) -> ScanResult:
    config = get_network(network)
    address = validate_address(address, network)
    sources = []
    warnings = []
    snapshot = empty_snapshot(address, network)
    try:
        pairs = fetch_pairs(address, network=network)
        if pairs:
            snapshot = snapshot_from_pairs(address, pairs, network=network)
            sources.append(SourceCheck("Market data", "available", "DEX Screener · selected trading pair"))
        else:
            sources.append(SourceCheck("Market data", "unavailable", "No indexed trading pair was returned. Contract checks continue."))
    except (DataSourceError, ValueError) as exc:
        sources.append(SourceCheck("Market data", "unavailable", str(exc)))

    security = None
    if config.goplus_chain_id is None:
        sources.append(SourceCheck("Contract security", "unsupported", "This version has no GoPlus security adapter for this network."))
    elif not check_security:
        sources.append(SourceCheck("Contract security", "not requested", "Optional provider checks were disabled."))
    else:
        try:
            security = fetch_security(address, network=network)
            sources.append(SourceCheck("Contract security", "available", "GoPlus · individual flag coverage shown below"))
        except DataSourceError as exc:
            sources.append(SourceCheck("Contract security", "unavailable", str(exc)))

    blockchain = inspect_chain(address, network)
    sources.append(SourceCheck("Blockchain lookup", blockchain.status, blockchain.message))
    if blockchain.is_contract is False:
        warnings.append(blockchain.message)
    if not snapshot.market_available:
        def security_text(key):
            value = security.get(key) if isinstance(security, dict) else None
            return value.strip()[:256] if isinstance(value, str) and value.strip() else None
        snapshot = replace(snapshot, name=blockchain.name or security_text("token_name") or "Unknown token",
                           symbol=blockchain.symbol or security_text("token_symbol") or "Unknown")
    warnings.extend(blockchain.warnings)

    previous = None
    if snapshot.pair_address and snapshot.pair_url:
        try:
            previous = latest_liquidity(address, network=network, pair_address=snapshot.pair_address)
        except (OSError, sqlite3.Error):
            warnings.append("Saved history is unavailable; liquidity change could not be assessed.")
    report = assess(snapshot, security, previous)
    # Security availability alone is not complete coverage of its flags.
    sources = [replace(source, status=("complete" if report.security_checked_count == report.security_possible_count else "partial"),
                       details=f"GoPlus · {report.security_checked_count}/{report.security_possible_count} configured flags have known values")
               if source.name == "Contract security" and source.status == "available" else source
               for source in sources]
    saved = True
    try:
        save_scan(snapshot, report)
    except (OSError, sqlite3.Error):
        saved = False
        warnings.append("This result could not be saved. Local history is unavailable.")
    return ScanResult(snapshot, report, tuple(warnings), tuple(sources), blockchain, saved)
