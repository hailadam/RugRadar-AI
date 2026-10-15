import unittest
from unittest.mock import Mock

import httpx

from rugradar.market import DataSourceError
from rugradar.security import fetch_security, flag_state, is_flagged


ADDRESS = "0x" + "a" * 40
SOLANA_MINT = "So11111111111111111111111111111111111111112"


def api_client(body):
    response = Mock()
    response.json.return_value = body
    client = Mock()
    client.get.return_value = response
    return client


class MultiNetworkSecurityTests(unittest.TestCase):
    def test_each_evm_network_uses_its_own_chain_endpoint(self):
        chains = {
            "base": "8453", "ethereum": "1", "bsc": "56", "arbitrum": "42161",
            "optimism": "10", "polygon": "137", "avalanche": "43114",
        }
        for network, chain_id in chains.items():
            with self.subTest(network=network):
                client = api_client({"code": 1, "result": {ADDRESS: {"is_honeypot": "0"}}})
                fetch_security(ADDRESS, client, network=network)
                args, kwargs = client.get.call_args
                self.assertEqual(args[0], f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}")
                self.assertEqual(kwargs["params"], {"contract_addresses": ADDRESS})
                self.assertEqual(kwargs["timeout"], 12)

    def test_evm_result_keys_are_matched_case_insensitively(self):
        client = api_client({"code": "1", "result": {"0x" + "A" * 40: {"hidden_owner": "1"}}})
        self.assertEqual(fetch_security(ADDRESS, client), {"hidden_owner": "1"})

    def test_partial_provider_response_remains_partial(self):
        partial = {"is_honeypot": "0", "is_mintable": None}
        client = api_client({"code": 1, "result": {ADDRESS: partial}})
        self.assertEqual(fetch_security(ADDRESS, client), partial)

    def test_empty_missing_and_invalid_results_raise(self):
        bodies = [
            {"code": 1, "result": {ADDRESS: {}}},
            {"code": 1, "result": {}},
            {"code": 1, "result": {ADDRESS: None}},
            {"code": 1, "result": {"0x" + "b" * 40: {"is_honeypot": "0"}}},
            {"code": 1, "result": []},
            {"code": 0, "result": {ADDRESS: {"is_honeypot": "0"}}},
        ]
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(DataSourceError):
                fetch_security(ADDRESS, api_client(body))

    def test_solana_is_explicitly_unsupported_without_evm_request(self):
        client = Mock()
        with self.assertRaisesRegex(DataSourceError, "unavailable for Solana"):
            fetch_security(SOLANA_MINT, client, network="solana")
        client.get.assert_not_called()

    def test_timeout_stays_a_source_error(self):
        client = Mock()
        client.get.side_effect = httpx.ReadTimeout("read timeout")
        with self.assertRaisesRegex(DataSourceError, "request failed"):
            fetch_security(ADDRESS, client, network="ethereum")

    def test_flag_state_accepts_only_explicit_binary_values(self):
        for value in (True, 1, "1"):
            with self.subTest(value=value):
                self.assertIs(flag_state(value), True)
                self.assertTrue(is_flagged(value))
        for value in (False, 0, "0"):
            with self.subTest(value=value):
                self.assertIs(flag_state(value), False)
                self.assertFalse(is_flagged(value))
        for value in (None, "", "true", "false", "unknown", "-1", -1, 2, 1.0, 0.0, " 0", [], {}):
            with self.subTest(value=value):
                self.assertIsNone(flag_state(value))
                self.assertFalse(is_flagged(value))
