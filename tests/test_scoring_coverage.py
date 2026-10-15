import unittest

from rugradar.market import TokenSnapshot
from rugradar.scoring import RiskReport, assess


FLAGS = ("is_honeypot", "is_mintable", "hidden_owner", "owner_change_balance", "is_blacklisted")


def snapshot(**overrides):
    values = dict(
        address="0x" + "a" * 40, symbol="EX", name="Example", dex="uniswap",
        pair_address="0x" + "b" * 40, price_usd=1.0, liquidity_usd=200_000,
        volume_h24_usd=100_000, change_h24_pct=0.5, buys_h24=100, sells_h24=99,
        captured_at="2026-10-15T00:00:00+00:00", pair_url="", price_is_available=True,
    )
    values.update(overrides)
    return TokenSnapshot(**values)


def marketless_snapshot():
    return snapshot(price_usd=None, liquidity_usd=None, volume_h24_usd=None,
                    change_h24_pct=None, buys_h24=None, sells_h24=None, price_is_available=False)


class CoverageScoringTests(unittest.TestCase):
    def test_missing_empty_and_metadata_only_security_do_not_inflate_coverage(self):
        for security in (None, {}, {"token_name": "Example"}):
            with self.subTest(security=security):
                report = assess(snapshot(), security)
                self.assertEqual(report.checked_count, 3)
                self.assertEqual(report.security_checked_count, 0)
                self.assertIn("0/5 contract flags", report.coverage)
                self.assertFalse(report.is_complete)
                self.assertEqual(report.level, "Incomplete assessment (not verified safe)")
                for flag in FLAGS:
                    self.assertIn(flag, " ".join(report.findings))

    def test_partial_negative_security_keeps_unchecked_flags_unknown(self):
        report = assess(snapshot(), {"is_honeypot": "0"})
        self.assertEqual(report.score, 0)
        self.assertEqual(report.checked_count, 3)
        self.assertEqual(report.security_checked_count, 1)
        self.assertIn("1/5 contract flags", report.coverage)
        unknown_finding = next(item for item in report.findings if item.startswith("Unknown contract-security"))
        self.assertNotIn("is_honeypot", unknown_finding)
        self.assertIn("is_mintable", unknown_finding)

    def test_unknown_flag_strings_do_not_count_as_negative_results(self):
        security = dict.fromkeys(FLAGS, "unknown")
        report = assess(snapshot(), security)
        self.assertEqual(report.score, 0)
        self.assertEqual(report.security_checked_count, 0)
        self.assertEqual(report.checked_count, 3)
        self.assertIn("Unknown contract-security", " ".join(report.findings))

    def test_complete_contract_category_requires_all_five_flags(self):
        for count in range(6):
            with self.subTest(count=count):
                security = dict.fromkeys(FLAGS[:count], "0")
                report = assess(snapshot(), security, previous_liquidity=200_000)
                self.assertEqual(report.checked_count, 5 if count == 5 else 4)
                self.assertEqual(report.security_checked_count, count)
                self.assertEqual(report.is_complete, count == 5)
        self.assertEqual(report.level, "No configured warnings (not verified safe)")

    def test_partial_positive_flags_still_add_risk_points(self):
        report = assess(snapshot(), {"is_mintable": "1", "hidden_owner": "1"})
        self.assertEqual(report.score, 30)
        self.assertEqual(report.security_checked_count, 2)
        self.assertEqual(report.checked_count, 3)
        self.assertEqual(report.level, "Moderate observed risk")

    def test_honeypot_flag_is_high_risk_even_without_market_coverage(self):
        report = assess(marketless_snapshot(), {"is_honeypot": "1"})
        self.assertEqual(report.score, 45)
        self.assertEqual(report.checked_count, 0)
        self.assertEqual(report.security_checked_count, 1)
        self.assertEqual(report.level, "High observed risk")
        self.assertIn("possible honeypot", " ".join(report.findings))
        self.assertIn("Missing data", " ".join(report.findings))

    def test_no_market_and_no_security_remains_insufficient(self):
        report = assess(marketless_snapshot(), {})
        self.assertEqual(report.score, 0)
        self.assertEqual(report.level, "Insufficient data")
        self.assertFalse(report.is_complete)

    def test_complete_security_alone_is_not_a_complete_assessment(self):
        report = assess(marketless_snapshot(), dict.fromkeys(FLAGS, "0"))
        self.assertEqual(report.checked_count, 1)
        self.assertEqual(report.level, "Insufficient data")
        self.assertFalse(report.is_complete)

    def test_legacy_report_constructor_remains_compatible(self):
        report = RiskReport(10, "Observed warnings", (), "1/5 categories", 1, 5)
        self.assertEqual(report.security_checked_count, 0)
        self.assertEqual(report.security_possible_count, 5)
        self.assertFalse(report.is_complete)
