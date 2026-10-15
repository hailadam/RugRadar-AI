import unittest
from unittest.mock import Mock

from rugradar.market import DataSourceError, empty_snapshot, fetch_pairs, snapshot_from_pairs
from rugradar.networks import NETWORKS, get_network


ADDRESS = "0x" + "aB" * 20
OTHER = "0x" + "c" * 40
PAIR = "0x" + "d" * 40
SOLANA = "So11111111111111111111111111111111111111112"
SOLANA_PAIR = "11111111111111111111111111111111"


def pair(network="base", address=ADDRESS, **overrides):
    result = {
        "chainId": network, "pairAddress": PAIR, "dexId": "example",
        "baseToken": {"address": address, "name": "Example", "symbol": "EXP"},
        "quoteToken": {"address": OTHER, "symbol": "QUOTE"},
        "priceUsd": "1.5", "liquidity": {"usd": 20000},
        "volume": {"h24": 50000}, "priceChange": {"h24": 3},
        "txns": {"h24": {"buys": 20, "sells": 9}},
    }
    result.update(overrides)
    return result


def client_with(payload):
    response = Mock()
    response.json.return_value = payload
    client = Mock()
    client.get.return_value = response
    return client


class MultichainMarketTests(unittest.TestCase):
    def test_fetch_uses_selected_chain_and_rejects_other_chains(self):
        for network in NETWORKS:
            with self.subTest(network=network):
                address = ADDRESS if get_network(network).evm else SOLANA
                data = pair(network, address)
                other_chain = "ethereum" if network != "ethereum" else "base"
                client = client_with([data, pair(other_chain, address)])
                self.assertEqual(fetch_pairs(address, client, network), [data])
                client.get.assert_called_once_with(
                    f"https://api.dexscreener.com/token-pairs/v1/{network}/{address}", timeout=12)

    def test_evm_addresses_match_ignoring_case(self):
        snapshot = snapshot_from_pairs(ADDRESS, [pair("ethereum", ADDRESS.lower())], "ethereum")
        self.assertEqual(snapshot.network, "ethereum")
        self.assertEqual(snapshot.pair_url, f"https://dexscreener.com/ethereum/{PAIR}")

    def test_solana_matching_is_case_sensitive_and_pool_url_is_chain_specific(self):
        correct = pair("solana", SOLANA, pairAddress=SOLANA_PAIR)
        wrong_case = pair("solana", SOLANA.swapcase(), liquidity={"usd": 900000})
        client = client_with([correct, wrong_case])
        self.assertEqual(fetch_pairs(SOLANA, client, "solana"), [correct])
        snapshot = snapshot_from_pairs(SOLANA, [correct, wrong_case], "solana")
        self.assertEqual(snapshot.address, SOLANA)
        self.assertEqual(snapshot.liquidity_usd, 20000)
        self.assertEqual(snapshot.pair_url, f"https://dexscreener.com/solana/{SOLANA_PAIR}")

    def test_snapshot_filters_chain_and_unrelated_addresses_before_selection(self):
        data = [pair(), pair("ethereum", liquidity={"usd": 999999}),
                pair(address=OTHER, quoteToken={}, liquidity={"usd": 999999})]
        self.assertEqual(snapshot_from_pairs(ADDRESS, data).liquidity_usd, 20000)
        with self.assertRaises(ValueError):
            snapshot_from_pairs(ADDRESS, [pair("ethereum")])

    def test_quote_side_transactions_are_reversed_and_price_is_unknown(self):
        snapshot = snapshot_from_pairs(ADDRESS, [pair(
            baseToken={"address": OTHER}, quoteToken={"address": ADDRESS, "symbol": "EXP"})])
        self.assertEqual(snapshot.buys_h24, 9)
        self.assertEqual(snapshot.sells_h24, 20)
        self.assertIsNone(snapshot.price_usd)
        self.assertIsNone(snapshot.change_h24_pct)
        self.assertFalse(snapshot.price_is_available)

    def test_base_side_pool_is_preferred_before_liquidity(self):
        quote_pool = pair(baseToken={"address": OTHER}, quoteToken={"address": ADDRESS},
                          liquidity={"usd": 999999})
        snapshot = snapshot_from_pairs(ADDRESS, [quote_pool, pair()])
        self.assertEqual(snapshot.price_usd, 1.5)
        self.assertEqual(snapshot.liquidity_usd, 20000)

    def test_malformed_metadata_is_ignored_or_marked_unknown(self):
        malformed = [None, "oops", [], {"chainId": "base", "baseToken": ["bad"], "quoteToken": "bad"}]
        pool = pair(baseToken={"address": ADDRESS, "symbol": ["bad"], "name": {"bad": "name"}},
                    quoteToken=["bad"], dexId={"bad": "dex"}, pairAddress={"bad": "address"},
                    priceUsd="NaN", liquidity=[900], volume={"h24": -5},
                    txns={"h24": {"buys": -3, "sells": 1.5}}, priceChange={"h24": True})
        client = client_with(malformed + [pool])
        self.assertEqual(fetch_pairs(ADDRESS, client), [pool])
        snapshot = snapshot_from_pairs(ADDRESS, malformed + [pool])
        self.assertEqual(snapshot.symbol, "Unknown")
        self.assertEqual(snapshot.name, "Unknown token")
        self.assertEqual(snapshot.dex, "Unknown DEX")
        self.assertEqual(snapshot.pair_url, "")
        self.assertIsNone(snapshot.price_usd)
        self.assertIsNone(snapshot.liquidity_usd)
        self.assertIsNone(snapshot.volume_h24_usd)
        self.assertIsNone(snapshot.buys_h24)
        self.assertIsNone(snapshot.sells_h24)
        self.assertIsNone(snapshot.change_h24_pct)
        self.assertFalse(snapshot.price_is_available)

    def test_unexpected_payload_is_explicit_error(self):
        with self.assertRaises(DataSourceError):
            fetch_pairs(ADDRESS, client_with({"pairs": [pair()]}))

    def test_pair_urls_reject_path_and_query_injection(self):
        for pair_address in ("../ethereum/" + PAIR, PAIR + "?evil=1", "https://example.test", ""):
            with self.subTest(pair_address=pair_address):
                snapshot = snapshot_from_pairs(ADDRESS, [pair(pairAddress=pair_address)])
                self.assertEqual(snapshot.pair_url, "")
        pool_id = "0x" + "e" * 64
        self.assertEqual(snapshot_from_pairs(ADDRESS, [pair(pairAddress=pool_id)]).pair_url,
                         "https://dexscreener.com/base/" + pool_id)

    def test_no_market_retains_identity_without_inventing_metrics(self):
        snapshot = empty_snapshot(SOLANA, "solana")
        self.assertEqual(snapshot.address, SOLANA)
        self.assertEqual(snapshot.network, "solana")
        self.assertFalse(snapshot.market_available)
        self.assertFalse(snapshot.price_is_available)
        self.assertEqual(snapshot.pair_url, "")
        self.assertEqual(snapshot.pair_address, "")
        self.assertTrue(snapshot.captured_at)
        for field in ("price_usd", "liquidity_usd", "volume_h24_usd", "change_h24_pct", "buys_h24", "sells_h24"):
            self.assertIsNone(getattr(snapshot, field))
        with self.assertRaises(ValueError):
            snapshot_from_pairs(SOLANA, [], "solana")


if __name__ == "__main__":
    unittest.main()
