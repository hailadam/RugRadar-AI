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

    def summary(self):
        return next((item.value for item in self.app.markdown if 'class="risk-summary ' in item.value), "")

    def charts(self):
        # Streamlit renamed the chart element across supported releases.
        return list(self.app.get("vega_lite_chart")) + list(self.app.get("arrow_vega_lite_chart"))

    def test_incomplete_zero_is_not_displayed_as_zero_risk(self):
        self.submit()
        self.assertIn('risk-incomplete', self.summary())
        self.assertNotIn('0/100', self.summary())
        self.assertTrue(any("Assessment incomplete" in warning.value for warning in self.app.warning))
        self.assertEqual([metric.label for metric in self.app.metric], ["Liquidity", "24h Volume", "Token Price"])
        self.assertEqual([metric.value for metric in self.app.metric], ["$100,000", "$10,000", "$1"])

    def test_chain_change_clears_previous_result_before_rescan(self):
        self.submit()
        self.app.selectbox[0].select("ethereum").run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.metric), 0)
        self.assertEqual(self.summary(), "")
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
        self.assertIn('risk-incomplete', self.summary())
        self.assertTrue(any(source.status == "unsupported" for source in self.app.session_state["scan_result"].sources))

    def test_security_warning_survives_no_market_pair(self):
        self.market.return_value = []
        self.security.return_value = {"is_honeypot": "1"}
        self.submit()
        self.assertIn('45/100', self.summary())
        self.assertIn('risk-high', self.summary())
        self.assertEqual(self.app.metric[0].value, "Unavailable")
        self.assertTrue(any("honeypot" in item.value for item in self.app.markdown))

    def test_provider_failures_show_unknowns_without_crashing(self):
        self.market.side_effect = DataSourceError("Market unavailable")
        self.security.side_effect = DataSourceError("Security unavailable")
        self.submit()
        self.assertIn('risk-incomplete', self.summary())
        self.assertEqual([metric.value for metric in self.app.metric], ["Unavailable", "Unavailable", "Unavailable"])
        self.assertEqual(len(self.app.dataframe), 1)

    def test_invalid_input_removes_previous_result(self):
        self.submit()
        self.submit("invalid address")
        self.assertEqual(len(self.app.error), 1)
        self.assertEqual(len(self.app.metric), 0)
        self.assertEqual(self.summary(), "")

    def test_complete_zero_has_low_badge_and_three_market_cards(self):
        self.previous.return_value = 100_000
        self.submit()
        self.assertIn('risk-low', self.summary())
        self.assertIn('0/100', self.summary())
        self.assertIn('does not certify safety', self.summary())
        self.assertEqual(len(self.app.metric), 3)

    def test_quote_side_price_stays_unavailable(self):
        item = pair()
        item["baseToken"] = {"address": "0x" + "c" * 40, "name": "Other", "symbol": "OTH"}
        item["quoteToken"] = {"address": ADDRESS, "name": "Requested", "symbol": "REQ"}
        self.market.return_value = [item]
        self.submit()
        self.assertEqual(self.app.metric[2].value, "Unavailable")
        self.assertTrue(any("Quote-side" in item.value for item in self.app.info))

    def test_provider_token_metadata_is_escaped_in_result_heading(self):
        item = pair()
        item["baseToken"]["name"] = '<img src=x onerror="alert(1)">'
        item["baseToken"]["symbol"] = '<script>alert(1)</script>'
        self.market.return_value = [item]
        self.submit()
        heading = next(item.value for item in self.app.markdown if 'class="result-heading"' in item.value)
        self.assertIn('&lt;img', heading)
        self.assertIn('&lt;script&gt;', heading)
        self.assertNotIn('<img', heading)
        self.assertNotIn('<script>', heading)

    def test_empty_history_has_no_fabricated_charts(self):
        self.submit()
        self.assertEqual(len(self.charts()), 0)
        self.assertTrue(any("A story takes more than one snapshot" in item.value for item in self.app.markdown))

    def test_saved_history_charts_require_known_values_in_the_same_pool(self):
        self.history.return_value = [
            {"captured_at": f"2026-10-15T12:0{i}:00+00:00", "pair_address": PAIR,
             "risk_score": score, "price_usd": price, "liquidity_usd": liquidity}
            for i, (score, price, liquidity) in enumerate([(10, 1, 100_000), (None, None, None), (30, 2, 90_000)])]
        self.history.return_value.append({"captured_at": "2026-10-15T12:04:00+00:00", "pair_address": "0x" + "d" * 40,
                                          "risk_score": 99, "price_usd": 200, "liquidity_usd": 1})
        self.submit()
        charts = self.charts()
        self.assertEqual(len(charts), 3)
        import json
        for chart in charts:
            spec = json.loads(chart.proto.spec)
            self.assertEqual(spec["encoding"]["detail"]["field"], "segment")

    def test_one_known_price_does_not_create_a_price_chart(self):
        self.history.return_value = [
            {"captured_at": "2026-10-15T12:00:00+00:00", "pair_address": PAIR,
             "risk_score": None, "price_usd": 1, "liquidity_usd": 100_000},
            {"captured_at": "2026-10-15T12:01:00+00:00", "pair_address": PAIR,
             "risk_score": None, "price_usd": None, "liquidity_usd": 90_000}]
        self.submit()
        self.assertEqual(len(self.charts()), 1)
