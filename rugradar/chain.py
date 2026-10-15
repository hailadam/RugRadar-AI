"""Optional, read-only blockchain lookups using user-configured RPC endpoints."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit

import httpx

from .networks import Network, get_network, validate_address


@dataclass(frozen=True)
class ChainDetails:
    status: str
    message: str
    is_contract: bool | None = None
    name: str | None = None
    symbol: str | None = None
    decimals: int | None = None
    warnings: tuple[str, ...] = ()


class RpcError(RuntimeError):
    """An RPC provider could not supply a usable read-only result."""


def _rpc(client: httpx.Client, url: str, method: str, params: list):
    if method not in {"eth_chainId", "eth_getCode", "eth_call", "getGenesisHash", "getAccountInfo"}:
        raise ValueError("Only read-only blockchain methods are supported.")
    try:
        response = client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise RpcError("RPC response exceeded the supported size.")
        payload = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        # Endpoint URLs can contain credentials: do not include raw exceptions.
        raise RpcError("Blockchain lookup failed. Check the configured RPC provider.") from exc
    if not isinstance(payload, dict) or payload.get("error") or "result" not in payload:
        raise RpcError("The RPC provider did not return a usable result.")
    return payload["result"]


def _text(value: object) -> str | None:
    """Decode bounded ERC-20 string or legacy bytes32 metadata."""
    if not isinstance(value, str) or not value.startswith("0x") or len(value) > 8194:
        return None
    try:
        raw = bytes.fromhex(value[2:])
        if len(raw) == 32:
            text = raw.rstrip(b"\0").decode("utf-8")
        else:
            if len(raw) < 64:
                return None
            offset = int.from_bytes(raw[:32], "big")
            if offset < 32 or offset % 32 or offset + 32 > len(raw):
                return None
            size = int.from_bytes(raw[offset:offset + 32], "big")
            if size > 256 or offset + 32 + size > len(raw):
                return None
            text = raw[offset + 32:offset + 32 + size].decode("utf-8")
        return text if text and len(text) <= 256 and all(c.isprintable() for c in text) else None
    except (ValueError, UnicodeError):
        return None


def inspect_chain(address: str, network: str = "base", client: httpx.Client | None = None) -> ChainDetails:
    config = get_network(network)
    address = validate_address(address, network)
    url = os.getenv(config.rpc_env, "").strip()
    if not url:
        return ChainDetails("not configured", f"Optional blockchain lookup needs {config.rpc_env}.")
    try:
        parsed = urlsplit(url)
        valid = parsed.hostname and (parsed.scheme == "https" or (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ))
        parsed.port  # Validate malformed/out-of-range ports without exposing the URL.
    except ValueError:
        valid = False
    if not valid:
        return ChainDetails("unavailable", f"{config.rpc_env} must use HTTPS or a local node.")
    if client is None:
        with httpx.Client(timeout=12, follow_redirects=False) as own:
            return _inspect(address, config, own, url)
    return _inspect(address, config, client, url)


def _inspect(address: str, config: Network, client: httpx.Client, url: str) -> ChainDetails:
    try:
        if not config.evm:
            genesis = _rpc(client, url, "getGenesisHash", [])
            if genesis != "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d":
                raise RpcError("The configured Solana RPC is not the supported mainnet cluster.")
            result = _rpc(client, url, "getAccountInfo", [address, {"encoding": "jsonParsed", "commitment": "confirmed"}])
            if not isinstance(result, dict) or "value" not in result:
                raise RpcError("Solana RPC returned an unexpected account response.")
            value = result["value"]
            if value is None:
                return ChainDetails("available", "No account exists at this address on the selected network.", False)
            programs = {"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}
            if not isinstance(value, dict) or not isinstance(value.get("owner"), str):
                raise RpcError("Solana RPC returned malformed account ownership data.")
            try:
                validate_address(value["owner"], "solana")
            except ValueError as exc:
                raise RpcError("Solana RPC returned malformed account ownership data.") from exc
            if value["owner"] not in programs:
                return ChainDetails("available", "This address is not an SPL Token mint account.", False)
            data = value.get("data")
            parsed = data.get("parsed") if isinstance(data, dict) else None
            info = parsed.get("info") if isinstance(parsed, dict) else None
            if not isinstance(info, dict) or parsed.get("type") != "mint":
                return ChainDetails("unavailable", "SPL mint metadata could not be decoded.")
            warnings = []
            for key, label, observation in (
                ("mintAuthority", "Mint", "An active mint authority can create additional tokens."),
                ("freezeAuthority", "Freeze", "An active freeze authority can freeze token accounts."),
            ):
                if key not in info:
                    warnings.append(f"{label} authority information is unavailable.")
                elif info[key] is not None:
                    try:
                        validate_address(info[key], "solana")
                    except ValueError:
                        warnings.append(f"{label} authority information is unavailable.")
                    else:
                        warnings.append(observation)
            decimals = info.get("decimals")
            return ChainDetails("available", "SPL mint account found. Authority observations are separate from the market score.",
                                True, decimals=decimals if type(decimals) is int and 0 <= decimals <= 255 else None,
                                warnings=tuple(warnings))

        chain_id = _rpc(client, url, "eth_chainId", [])
        if not isinstance(chain_id, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", chain_id) or int(chain_id, 16) != config.chain_id:
            raise RpcError("The configured RPC does not match the selected network.")
        code = _rpc(client, url, "eth_getCode", [address, "latest"])
        if not isinstance(code, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", code):
            raise RpcError("The RPC provider returned invalid contract bytecode.")
        if code == "0x":
            return ChainDetails("available", "No contract bytecode exists at this address on the selected network.", False)
        metadata = {}
        for key, selector in (("name", "0x06fdde03"), ("symbol", "0x95d89b41"), ("decimals", "0x313ce567")):
            try:
                result = _rpc(client, url, "eth_call", [{"to": address, "data": selector}, "latest"])
                if key == "decimals":
                    decoded = int(result[2:], 16) if isinstance(result, str) and result.startswith("0x") and len(result) == 66 else None
                    metadata[key] = decoded if decoded is not None and 0 <= decoded <= 255 else None
                else:
                    metadata[key] = _text(result)
            except (RpcError, ValueError):
                metadata[key] = None
        return ChainDetails("available", "Contract bytecode found. Metadata reads do not establish ERC-20 compliance or safety.",
                            True, **metadata)
    except RpcError as exc:
        return ChainDetails("unavailable", str(exc))
