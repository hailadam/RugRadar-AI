import sqlite3
import unittest
from unittest.mock import patch

from rugradar.chain import ChainDetails
from rugradar.market import DataSourceError
from rugradar.scanner import analyze_token


ADDRESS = "0x" + "a" * 40
PAIR = "0x" + "b" * 40


def pair(network="base"):
    return {"chainId": network, "pairAddress": PAIR, "dexId": "example", "baseToken": {
        "address": ADDRESS, "name": "Example", "symbol": "EXP"}, "quoteToken": {},
        "liquidity": {"usd": 100_000}, "volume": {"h24": 10_000}, "priceUsd": "1",
        "priceChange": {"h24": 0}, "txns": {"h24": {"buys": 100, "sells": 100}}}


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch("rugradar.scanner.fetch_pairs", return_value=[pair()]),
                        patch("rugradar.scanner.fetch_security", return_value={"is_honeypot": "0"}),
                        patch("rugradar.scanner.inspect_chain", return_value=ChainDetails("not configured", "No RPC")),
                        patch("rugradar.scanner.latest_liquidity", return_value=None),
                        patch("rugradar.scanner.save_scan")]
        self.market, self.security, self.chain, self.previous, self.save = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)

    def test_no_pool_does_not_prevent_security_check(self):
        self.market.return_value = []
        self.security.return_value = {"is_honeypot": "1"}
        result = analyze_token(ADDRESS)
        self.security.assert_called_once_with(ADDRESS, network="base")
        self.assertFalse(result.snapshot.market_available)
        self.assertEqual(result.report.level, "High observed risk")
        self.assertFalse(result.report.is_complete)
        self.previous.assert_not_called()

    def test_market_error_does_not_prevent_security_check(self):
        self.market.side_effect = DataSourceError("Market unavailable")
        result = analyze_token(ADDRESS)
        self.security.assert_called_once()
        self.assertEqual(result.sources[0].status, "unavailable")

    def test_security_failure_preserves_market_result(self):
        self.security.side_effect = DataSourceError("Security unavailable")
        result = analyze_token(ADDRESS)
        self.assertEqual(result.snapshot.liquidity_usd, 100_000)
        self.assertFalse(result.report.is_complete)
        self.assertEqual(result.sources[1].status, "unavailable")

    def test_empty_partial_security_has_zero_complete_coverage(self):
        self.security.return_value = {"is_honeypot": ""}
        result = analyze_token(ADDRESS)
        self.assertEqual(result.report.security_checked_count, 0)
        self.assertEqual(result.sources[1].status, "partial")

    def test_network_and_pool_are_passed_to_history(self):
        self.market.return_value = [pair("ethereum")]
        result = analyze_token(ADDRESS, "ethereum")
        self.market.assert_called_once_with(ADDRESS, network="ethereum")
        self.security.assert_called_once_with(ADDRESS, network="ethereum")
        self.previous.assert_called_once_with(ADDRESS, network="ethereum", pair_address=PAIR)
        self.assertEqual(result.snapshot.network, "ethereum")

    def test_solana_never_calls_evm_security(self):
        self.market.return_value = []
        result = analyze_token("So11111111111111111111111111111111111111112", "solana")
        self.security.assert_not_called()
        self.assertEqual(result.sources[1].status, "unsupported")
        self.assertFalse(result.report.is_complete)

    def test_rpc_metadata_works_without_market_data(self):
        self.market.return_value = []
        self.chain.return_value = ChainDetails("available", "Contract found", True, "Unlisted", "NEW", 18)
        result = analyze_token(ADDRESS)
        self.assertEqual((result.snapshot.name, result.snapshot.symbol), ("Unlisted", "NEW"))
        self.assertIsNone(result.snapshot.liquidity_usd)

    def test_security_metadata_works_without_market_or_rpc_data(self):
        self.market.return_value = []
        self.security.return_value = {"token_name": "Unlisted", "token_symbol": "NEW", "is_honeypot": "0"}
        result = analyze_token(ADDRESS)
        self.assertEqual((result.snapshot.name, result.snapshot.symbol), ("Unlisted", "NEW"))
        self.assertIsNone(result.snapshot.liquidity_usd)

    def test_unusable_pool_identifier_cannot_create_a_liquidity_trend(self):
        data = pair()
        data["pairAddress"] = "unknown pool"
        self.market.return_value = [data]
        analyze_token(ADDRESS)
        self.previous.assert_not_called()

    def test_invalid_address_stops_before_external_calls(self):
        with self.assertRaises(ValueError):
            analyze_token("not an address")
        self.market.assert_not_called()
        self.security.assert_not_called()
        self.save.assert_not_called()

    def test_failed_history_write_does_not_hide_provider_results(self):
        self.save.side_effect = sqlite3.OperationalError("read-only database")
        result = analyze_token(ADDRESS)
        self.assertFalse(result.history_saved)
        self.assertEqual(result.snapshot.symbol, "EXP")
        self.assertTrue(any("could not be saved" in warning for warning in result.warnings))

    def test_failed_history_read_does_not_hide_provider_results(self):
        self.previous.side_effect = sqlite3.OperationalError("database locked")
        result = analyze_token(ADDRESS)
        self.assertTrue(any("liquidity change" in warning for warning in result.warnings))
        self.assertTrue(result.history_saved)

    def test_disabled_security_is_reported_as_not_requested(self):
        result = analyze_token(ADDRESS, check_security=False)
        self.security.assert_not_called()
        self.assertEqual(result.sources[1].status, "not requested")
