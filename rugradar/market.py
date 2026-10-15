"""Read-only DEX Screener market data for Base ERC-20 tokens."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

import httpx

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
API_URL = "https://api.dexscreener.com/token-pairs/v1/base/{address}"


class DataSourceError(RuntimeError):
    """An upstream market or security data provider could not be queried."""


def validate_address(address: str) -> str:
    address = address.strip()
    if not ADDRESS_PATTERN.fullmatch(address):
        raise ValueError("Enter an Ethereum token contract address: 0x followed by 40 hex characters.")
    return address


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result
    except (ValueError, TypeError):
        return None


def nested_number(data: dict, *path: str) -> float | None:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return number(data)


@dataclass(frozen=True)
class TokenSnapshot:
    address: str
    symbol: str
    name: str
    dex: str
    pair_address: str
    price_usd: float | None
    liquidity_usd: float | None
    volume_h24_usd: float | None
    change_h24_pct: float | None
    buys_h24: int | None
    sells_h24: int | None
    captured_at: str
    pair_url: str
    price_is_available: bool


def fetch_pairs(address: str, client: httpx.Client | None = None) -> list[dict]:
    """Fetch only Base pairs containing the given address, with a bounded timeout."""
    address = validate_address(address)
    try:
        if client is None:
            with httpx.Client(timeout=12, follow_redirects=False) as own_client:
                response = own_client.get(API_URL.format(address=address))
        else:
            response = client.get(API_URL.format(address=address), timeout=12)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"DEX Screener request failed: {exc}") from exc
    if not isinstance(payload, list):
        raise DataSourceError("DEX Screener returned an unexpected response format.")
    target = address.lower()
    return [
        p for p in payload
        if isinstance(p, dict)
        and str(p.get("chainId", "")).lower() == "base"
        and target in (
            str((p.get("baseToken") or {}).get("address", "")).lower(),
            str((p.get("quoteToken") or {}).get("address", "")).lower(),
        )
    ]


def snapshot_from_pairs(address: str, pairs: list[dict]) -> TokenSnapshot:
    """Prefer the most-liquid pair where the requested token is the BASE token.

    DEX Screener's priceUsd is for the *base* token, not the quote token.
    If only quote-side pools exist, price is intentionally marked unavailable.
    """
    address = validate_address(address)
    if not pairs:
        raise ValueError("No Base trading pairs found for that contract address.")
    candidates = [p for p in pairs if str((p.get("baseToken") or {}).get("address", "")).lower() == address.lower()]
    selected_pool = max(candidates or pairs, key=lambda p: nested_number(p, "liquidity", "usd") or 0)
    base_matches = str((selected_pool.get("baseToken") or {}).get("address", "")).lower() == address.lower()
    token = (selected_pool.get("baseToken") if base_matches else selected_pool.get("quoteToken")) or {}
    pair_addr = str(selected_pool.get("pairAddress") or "")
    pair_url = f"https://dexscreener.com/base/{pair_addr}" if ADDRESS_PATTERN.fullmatch(pair_addr) else ""
    buys = nested_number(selected_pool, "txns", "h24", "buys")
    sells = nested_number(selected_pool, "txns", "h24", "sells")
    return TokenSnapshot(
        address=address,
        symbol=str(token.get("symbol") or "Unknown"),
        name=str(token.get("name") or "Unknown token"),
        dex=str(selected_pool.get("dexId") or "Unknown DEX"),
        pair_address=pair_addr,
        price_usd=number(selected_pool.get("priceUsd")) if base_matches else None,
        liquidity_usd=nested_number(selected_pool, "liquidity", "usd"),
        volume_h24_usd=nested_number(selected_pool, "volume", "h24"),
        change_h24_pct=nested_number(selected_pool, "priceChange", "h24") if base_matches else None,
        buys_h24=int(buys) if buys is not None else None,
        sells_h24=int(sells) if sells is not None else None,
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pair_url=pair_url,
        price_is_available=base_matches,
    )
