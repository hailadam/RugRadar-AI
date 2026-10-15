"""Supported networks and chain-aware token address validation."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Network:
    key: str
    name: str
    chain_id: int | None
    evm: bool
    goplus_chain_id: str | None
    rpc_env: str


NETWORKS: dict[str, Network] = {
    "base": Network("base", "Base", 8453, True, "8453", "BASE_RPC_URL"),
    "ethereum": Network("ethereum", "Ethereum", 1, True, "1", "ETHEREUM_RPC_URL"),
    "bsc": Network("bsc", "BNB Chain", 56, True, "56", "BSC_RPC_URL"),
    "arbitrum": Network("arbitrum", "Arbitrum", 42161, True, "42161", "ARBITRUM_RPC_URL"),
    "optimism": Network("optimism", "Optimism", 10, True, "10", "OPTIMISM_RPC_URL"),
    "polygon": Network("polygon", "Polygon", 137, True, "137", "POLYGON_RPC_URL"),
    "avalanche": Network("avalanche", "Avalanche", 43114, True, "43114", "AVALANCHE_RPC_URL"),
    "solana": Network("solana", "Solana", None, False, None, "SOLANA_RPC_URL"),
}

ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_VALUES = {character: index for index, character in enumerate(_BASE58_ALPHABET)}


def get_network(key: str = "base") -> Network:
    """Resolve an allowlisted DEX Screener network slug."""
    if not isinstance(key, str) or key not in NETWORKS:
        raise ValueError("Select a supported network: " + ", ".join(NETWORKS) + ".")
    return NETWORKS[key]


def validate_address(address: str, network: str = "base") -> str:
    """Validate an EVM contract or a 32-byte Solana base58 address.

    Validation establishes address syntax; it does not establish that the
    address is a token or that its contract is safe.
    """
    selected = get_network(network)
    if not isinstance(address, str):
        raise ValueError("Enter a token address.")
    address = address.strip()
    if selected.evm:
        if not ADDRESS_PATTERN.fullmatch(address):
            raise ValueError("Enter an EVM token contract address: 0x followed by 40 hex characters.")
        return address

    if not 32 <= len(address) <= 44 or any(character not in _BASE58_VALUES for character in address):
        raise ValueError("Enter a Solana token mint address: a base58-encoded 32-byte public key.")
    decoded_value = 0
    for character in address:
        decoded_value = decoded_value * 58 + _BASE58_VALUES[character]
    leading_zeroes = len(address) - len(address.lstrip("1"))
    decoded_length = leading_zeroes + (decoded_value.bit_length() + 7) // 8
    if decoded_length != 32:
        raise ValueError("Enter a Solana token mint address: a base58-encoded 32-byte public key.")
    return address


def address_key(address: str, network: str = "base") -> str:
    """Return a comparison/storage key without losing Solana case."""
    validated = validate_address(address, network)
    return validated.lower() if get_network(network).evm else validated
