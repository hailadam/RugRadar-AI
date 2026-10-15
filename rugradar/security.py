"""Optional token contract signals from GoPlus. Authentication and availability vary."""
from __future__ import annotations
import os
import httpx
from .market import DataSourceError, validate_address

API_URL = "https://api.gopluslabs.io/api/v1/token_security/8453"


def fetch_security(address: str, client: httpx.Client | None = None) -> dict:
    address = validate_address(address)
    headers = {}
    key = os.getenv("GOPLUS_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        if client is None:
            with httpx.Client(timeout=12, follow_redirects=False) as own_client:
                response = own_client.get(API_URL, params={"contract_addresses": address}, headers=headers)
        else:
            response = client.get(API_URL, params={"contract_addresses": address}, headers=headers, timeout=12)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSourceError(f"GoPlus token-security request failed: {exc}") from exc
    if not isinstance(body, dict) or str(body.get("code")) != "1":
        raise DataSourceError("GoPlus did not return a successful token-security response.")
    result = body.get("result")
    if not isinstance(result, dict):
        raise DataSourceError("GoPlus returned no usable token-security result.")
    info = result.get(address.lower()) or result.get(address)
    if not isinstance(info, dict):
        raise DataSourceError("GoPlus has no security information for this token.")
    return info


def is_flagged(value: object) -> bool:
    # Only the explicit GoPlus true flag is used. Null, unknown, and errors stay unknown.
    return str(value) == "1" or value is True
