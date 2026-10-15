from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from rugradar.chain import ChainDetails
from rugradar.market import DataSourceError


ADDRESS = "0x" + "a" * 40
PAIR = "0x" + "b" * 40
MINT = "So11111111111111111111111111111111111111112"
FLAGS = {key: "0" for key in ("is_honeypot", "is_mintable", "hidden_owner", "owner_change_balance", "is_blacklisted")}


def pair(network="base", address=ADDRESS):
    return {"chainId": network, "pairAddress": PAIR if network != "solana" else MINT, "dexId": "example",
            "baseToken": {"address": address, "name": "Example", "symbol": "EXP"}, "quoteToken": {},
            "liquidity": {"usd": 100_000}, "volume": {"h24": 10_000}, "priceUsd": "1",
            "priceChange": {"h24": 0}, "txns": {"h24": {"buys": 100, "sells": 100}}}


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch("rugradar.scanner.fetch_pairs", return_value=[pair()]),
                        patch("rugradar.scanner.fetch_security", return_value=FLAGS),
                        patch("rugradar.scanner.inspect_chain", return_value=ChainDetails("not configured", "No RPC")),
                        patch("rugradar.scanner.latest_liquidity", return_value=None),
                        patch("rugradar.scanner.save_scan"),
                        patch("rugradar.history.token_history", return_value=[])]
        self.market, self.security, self.chain, self.previous, self.save, self.history = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=15).run()
        self.assertFalse(self.app.exception)

    def submit(self, address=ADDRESS):
        self.app.text_input[0].set_value(address)
        self.app.button[0].click().run()
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])

    def test_incomplete_zero_is_not_displayed_as_zero_risk(self):
        self.submit()
        self.assertEqual(self.app.metric[0].value, "Incomplete")
        self.assertTrue(any("Assessment incomplete" in warning.value for warning in self.app.warning))
        self.assertEqual(self.app.metric[1].value, "$100,000")

    def test_chain_change_clears_previous_result_before_rescan(self):
        self.submit()
        self.app.selectbox[0].select("ethereum").run()
        self.assertFalse(self.app.exception)
        self.assertEqual([metric.value for metric in self.app.metric], ["—", "—", "—"])
        self.assertEqual(self.market.call_count, 1)
        self.market.return_value = [pair("ethereum")]
        self.submit()
        self.assertEqual(self.app.session_state["scan_result"].snapshot.network, "ethereum")
        self.history.assert_called_with(ADDRESS, network="ethereum")

    def test_solana_controls_and_unsupported_security_are_explicit(self):
        self.app.selectbox[0].select("solana").run()
        self.assertEqual(self.app.text_input[0].label, "Token mint address")
        self.assertTrue(self.app.checkbox[0].disabled)
        self.assertFalse(self.app.checkbox[0].value)
        self.market.return_value = [pair("solana", MINT)]
        self.submit(MINT)
        self.security.assert_not_called()
        self.assertEqual(self.app.metric[0].value, "Incomplete")
        self.assertTrue(any(source.status == "unsupported" for source in self.app.session_state["scan_result"].sources))

    def test_security_warning_survives_no_market_pair(self):
        self.market.return_value = []
        self.security.return_value = {"is_honeypot": "1"}
        self.submit()
        self.assertEqual(self.app.metric[0].value, "45/100")
        self.assertEqual(self.app.metric[1].value, "Unavailable")
        self.assertTrue(any("honeypot" in item.value for item in self.app.markdown))

    def test_provider_failures_show_unknowns_without_crashing(self):
        self.market.side_effect = DataSourceError("Market unavailable")
        self.security.side_effect = DataSourceError("Security unavailable")
        self.submit()
        self.assertEqual([metric.value for metric in self.app.metric], ["Incomplete", "Unavailable", "Unavailable"])
        self.assertEqual(len(self.app.dataframe), 1)

    def test_invalid_input_removes_previous_result(self):
        self.submit()
        self.submit("invalid address")
        self.assertEqual(len(self.app.error), 1)
        self.assertEqual([metric.value for metric in self.app.metric], ["—", "—", "—"])
