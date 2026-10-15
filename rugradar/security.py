"""Optional token contract signals from GoPlus. Authentication and availability vary."""
from __future__ import annotations
import os
import httpx
from .market import DataSourceError
from .networks import get_network, validate_address

API_URL = "https://api.gopluslabs.io/api/v1/token_security/8453"
API_URL_TEMPLATE = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"


def fetch_security(address: str, client: httpx.Client | None = None, network: str = "base") -> dict:
    """Retrieve provider observations on the selected network.

    An unavailable adapter or an empty response is an error, not evidence that
    the token passed security checks. Partial responses stay partial so scoring
    can disclose each unknown flag.
    """
    selected = get_network(network)
    address = validate_address(address, network)
    if selected.goplus_chain_id is None:
        raise DataSourceError(f"Contract-security checks are unavailable for {selected.name}; contract risks remain unknown.")
    api_url = API_URL_TEMPLATE.format(chain_id=selected.goplus_chain_id)
    headers = {}
    key = os.getenv("GOPLUS_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        if client is None:
            with httpx.Client(timeout=12, follow_redirects=False) as own_client:
                response = own_client.get(api_url, params={"contract_addresses": address}, headers=headers)
        else:
            response = client.get(api_url, params={"contract_addresses": address}, headers=headers, timeout=12)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"GoPlus token-security request failed: {exc}") from exc
    if not isinstance(body, dict) or str(body.get("code")) != "1":
        raise DataSourceError("GoPlus did not return a successful token-security response.")
    result = body.get("result")
    if not isinstance(result, dict):
        raise DataSourceError("GoPlus returned no usable token-security result.")
    target = address.lower() if selected.evm else address
    info = next((value for key, value in result.items()
                 if isinstance(key, str)
                 and (key.lower() if selected.evm else key) == target), None)
    if not isinstance(info, dict) or not info:
        raise DataSourceError("GoPlus has no security information for this token.")
    return info


def flag_state(value: object) -> bool | None:
    """Parse only explicit provider flags; absent/unrecognized values are unknown."""
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if type(value) is str and value in ("0", "1"):
        return value == "1"
    return None


def is_flagged(value: object) -> bool:
    # Kept for callers needing a yes/no positive flag, never for data coverage.
    return flag_state(value) is True
