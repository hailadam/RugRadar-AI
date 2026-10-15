import json
import os
import unittest
from unittest.mock import patch

import httpx

from rugradar.chain import inspect_chain


ADDRESS = "0x" + "a" * 40
MINT = "So11111111111111111111111111111111111111112"


def abi_text(text):
    data = text.encode()
    return "0x" + (32).to_bytes(32, "big").hex() + len(data).to_bytes(32, "big").hex() + data.hex().ljust(64, "0")


def transport(handler, chain_id="0x2105"):
    def wrapped(request):
        method = json.loads(request.content)["method"]
        if method == "eth_chainId":
            return httpx.Response(200, json={"result": chain_id})
        if method == "getGenesisHash":
            return httpx.Response(200, json={"result": "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"})
        return handler(request)
    return httpx.MockTransport(wrapped)


class ChainTests(unittest.TestCase):
    def test_unconfigured_rpc_is_explicit(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": ""}):
            result = inspect_chain(ADDRESS)
        self.assertEqual(result.status, "not configured")
        self.assertIsNone(result.is_contract)

    def test_evm_lookup_uses_only_reads_and_decodes_metadata(self):
        methods = []

        def handler(request):
            body = json.loads(request.content)
            methods.append(body["method"])
            if body["method"] == "eth_getCode":
                result = "0x6000"
            else:
                selector = body["params"][0]["data"]
                result = {"0x06fdde03": abi_text("Example"), "0x95d89b41": abi_text("EXP"),
                          "0x313ce567": "0x" + (18).to_bytes(32, "big").hex()}[selector]
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

        with patch.dict(os.environ, {"ETHEREUM_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(handler, "0x1")) as client:
            result = inspect_chain(ADDRESS, "ethereum", client)
        self.assertEqual((result.name, result.symbol, result.decimals), ("Example", "EXP", 18))
        self.assertTrue(result.is_contract)
        self.assertEqual(methods, ["eth_getCode", "eth_call", "eth_call", "eth_call"])

    def test_eoa_does_not_claim_token_exists(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
            lambda request: httpx.Response(200, json={"result": "0x"})
        )) as client:
            result = inspect_chain(ADDRESS, client=client)
        self.assertFalse(result.is_contract)

    def test_rpc_error_does_not_expose_endpoint_credentials(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": "https://node.example/private-secret"}), httpx.Client(transport=transport(
            lambda request: httpx.Response(401, json={"error": "private-secret"})
        )) as client:
            result = inspect_chain(ADDRESS, client=client)
        self.assertEqual(result.status, "unavailable")
        self.assertNotIn("private-secret", result.message)

    def test_metadata_failure_preserves_contract_existence(self):
        def handler(request):
            body = json.loads(request.content)
            return httpx.Response(200, json={"result": "0x6000"} if body["method"] == "eth_getCode" else {"error": {"code": -32000}})
        with patch.dict(os.environ, {"BASE_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(handler)) as client:
            result = inspect_chain(ADDRESS, client=client)
        self.assertTrue(result.is_contract)
        self.assertIsNone(result.name)

    def test_invalid_bytecode_is_unavailable(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
            lambda request: httpx.Response(200, json={"result": "0xnothex"})
        )) as client:
            result = inspect_chain(ADDRESS, client=client)
        self.assertEqual(result.status, "unavailable")

    def test_nonlocal_plain_http_is_rejected(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": "http://node.example"}):
            result = inspect_chain(ADDRESS)
        self.assertEqual(result.status, "unavailable")

    def test_solana_mint_authority_warnings(self):
        account = {"owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "data": {
            "parsed": {"type": "mint", "info": {"decimals": 9, "mintAuthority": MINT, "freezeAuthority": MINT}}}}
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(body["method"], "getAccountInfo")
            self.assertEqual(body["params"][0], MINT)
            return httpx.Response(200, json={"result": {"value": account}})
        with patch.dict(os.environ, {"SOLANA_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(handler)) as client:
            result = inspect_chain(MINT, "solana", client)
        self.assertTrue(result.is_contract)
        self.assertEqual(result.decimals, 9)
        self.assertEqual(len(result.warnings), 2)
        self.assertTrue(all("active" in warning for warning in result.warnings))

    def test_solana_wallet_is_not_a_mint(self):
        with patch.dict(os.environ, {"SOLANA_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
            lambda request: httpx.Response(200, json={"result": {"value": {"owner": "11111111111111111111111111111111"}}})
        )) as client:
            result = inspect_chain(MINT, "solana", client)
        self.assertFalse(result.is_contract)

    def test_solana_missing_authorities_remain_unknown(self):
        account = {"owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "data": {
            "parsed": {"type": "mint", "info": {"decimals": 9}}}}
        with patch.dict(os.environ, {"SOLANA_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
            lambda request: httpx.Response(200, json={"result": {"value": account}})
        )) as client:
            result = inspect_chain(MINT, "solana", client)
        self.assertTrue(result.is_contract)
        self.assertTrue(all("unavailable" in warning for warning in result.warnings))

    def test_wrong_evm_network_is_rejected(self):
        with patch.dict(os.environ, {"BASE_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
            lambda request: self.fail("Contract reads must not run on the wrong chain"), "0x1"
        )) as client:
            result = inspect_chain(ADDRESS, client=client)
        self.assertEqual(result.status, "unavailable")
        self.assertIn("does not match", result.message)

    def test_wrong_solana_cluster_is_rejected(self):
        with patch.dict(os.environ, {"SOLANA_RPC_URL": "https://node.example"}), httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"result": "devnet"})
        )) as client:
            result = inspect_chain(MINT, "solana", client)
        self.assertEqual(result.status, "unavailable")

    def test_malformed_rpc_urls_do_not_crash_or_expose_values(self):
        for url in ("https://[", "https://secret@example.test:bad"):
            with self.subTest(url_type="invalid"), patch.dict(os.environ, {"BASE_RPC_URL": url}):
                result = inspect_chain(ADDRESS)
            self.assertEqual(result.status, "unavailable")
            self.assertNotIn("secret", result.message)

    def test_malformed_solana_account_is_unknown(self):
        for value in ([], {"owner": []}, {"owner": "invalid"}):
            with self.subTest(value_type=type(value).__name__), patch.dict(os.environ, {"SOLANA_RPC_URL": "https://node.example"}), httpx.Client(transport=transport(
                lambda request: httpx.Response(200, json={"result": {"value": value}})
            )) as client:
                result = inspect_chain(MINT, "solana", client)
            self.assertEqual(result.status, "unavailable")
            self.assertIsNone(result.is_contract)
