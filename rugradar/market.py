"""Read-only DEX Screener data with chain-aware pool selection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from rugradar.networks import ADDRESS_PATTERN, get_network, validate_address

API_URL = "https://api.dexscreener.com/token-pairs/v1/{network}/{address}"


class DataSourceError(RuntimeError):
    """An upstream market or security data provider could not be queried."""


def number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        result = float(value)
        if result != result or result in (float("inf"), float("-inf")):
            return None
        return result
    except (ValueError, TypeError, OverflowError):
        return None


def nested_number(data: dict, *path: str) -> float | None:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return number(data)


def _token(pair: dict, side: str) -> dict:
    value = pair.get(side)
    return value if isinstance(value, dict) else {}


def _matches(candidate: Any, address: str, network: str) -> bool:
    if not isinstance(candidate, str):
        return False
    if get_network(network).evm:
        return candidate.lower() == address.lower()
    return candidate == address


def _matching_pairs(address: str, pairs: list, network: str) -> list[dict]:
    return [
        pair for pair in pairs
        if isinstance(pair, dict)
        and pair.get("chainId") == network
        and any(_matches(_token(pair, side).get("address"), address, network)
                for side in ("baseToken", "quoteToken"))
    ]


def _text(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _count(value: float | None) -> int | None:
    return int(value) if value is not None and value >= 0 and value.is_integer() else None


def _nonnegative(value: float | None) -> float | None:
    return value if value is not None and value >= 0 else None


def _pair_url(pair_address: str, network: str) -> str:
    try:
        validate_address(pair_address, network)
    except ValueError:
        # EVM pool identifiers may also be bytes32, rather than contract addresses.
        if not (get_network(network).evm and pair_address.startswith("0x")
                and len(pair_address) == 66
                and all(character in "0123456789abcdefABCDEF" for character in pair_address[2:])):
            return ""
    return f"https://dexscreener.com/{network}/{pair_address}"


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
    network: str = "base"
    market_available: bool = True


def fetch_pairs(address: str, client: httpx.Client | None = None, network: str = "base") -> list[dict]:
    """Fetch only selected-chain pools containing the token, with a bounded timeout."""
    address = validate_address(address, network)
    url = API_URL.format(network=network, address=address)
    try:
        if client is None:
            with httpx.Client(timeout=12, follow_redirects=False) as own_client:
                response = own_client.get(url)
        else:
            response = client.get(url, timeout=12)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"DEX Screener request failed: {exc}") from exc
    if not isinstance(payload, list):
        raise DataSourceError("DEX Screener returned an unexpected response format.")
    return _matching_pairs(address, payload, network)


def snapshot_from_pairs(address: str, pairs: list[dict], network: str = "base") -> TokenSnapshot:
    """Prefer the most-liquid pair where the requested token is the BASE token.

    DEX Screener's priceUsd is for the *base* token, not the quote token.
    If only quote-side pools exist, price is intentionally marked unavailable.
    """
    address = validate_address(address, network)
    pairs = _matching_pairs(address, pairs, network)
    if not pairs:
        raise ValueError(f"No {get_network(network).name} trading pairs found for that token address.")
    candidates = [pair for pair in pairs if _matches(_token(pair, "baseToken").get("address"), address, network)]
    selected_pool = max(candidates or pairs, key=lambda pair: _nonnegative(nested_number(pair, "liquidity", "usd")) or 0)
    base_matches = _matches(_token(selected_pool, "baseToken").get("address"), address, network)
    token = _token(selected_pool, "baseToken" if base_matches else "quoteToken")
    pair_addr = _text(selected_pool.get("pairAddress"))
    buys = nested_number(selected_pool, "txns", "h24", "buys")
    sells = nested_number(selected_pool, "txns", "h24", "sells")
    if not base_matches:
        buys, sells = sells, buys
    price = _nonnegative(number(selected_pool.get("priceUsd"))) if base_matches else None
    return TokenSnapshot(
        address=address,
        symbol=_text(token.get("symbol"), "Unknown"),
        name=_text(token.get("name"), "Unknown token"),
        dex=_text(selected_pool.get("dexId"), "Unknown DEX"),
        pair_address=pair_addr,
        price_usd=price,
        liquidity_usd=_nonnegative(nested_number(selected_pool, "liquidity", "usd")),
        volume_h24_usd=_nonnegative(nested_number(selected_pool, "volume", "h24")),
        change_h24_pct=nested_number(selected_pool, "priceChange", "h24") if base_matches else None,
        buys_h24=_count(buys),
        sells_h24=_count(sells),
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pair_url=_pair_url(pair_addr, network),
        price_is_available=price is not None,
        network=network,
    )


def empty_snapshot(address: str, network: str = "base") -> TokenSnapshot:
    """Retain token identity when no usable market pool was returned."""
    address = validate_address(address, network)
    return TokenSnapshot(
        address=address, symbol="Unknown", name="Unknown token", dex="Unavailable",
        pair_address="", price_usd=None, liquidity_usd=None, volume_h24_usd=None,
        change_h24_pct=None, buys_h24=None, sells_h24=None,
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pair_url="", price_is_available=False, network=network, market_available=False,
    )
