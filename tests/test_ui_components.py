from html.parser import HTMLParser
import unittest

from rugradar.scoring import RiskReport
from ui_components import icon, risk_summary, scan_history_chart, warning_panel


class Elements(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.items = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))

    def with_class(self, name):
        return [attrs for _, attrs in self.items if name in attrs.get("class", "").split()]


def report(score=0, level="Incomplete assessment (not verified safe)", findings=(), complete=False, coverage="3/5 categories; 5/5 contract flags"):
    return RiskReport(score, level, findings, coverage, 5 if complete else 3, 5, 5, 5)


class UiComponentTests(unittest.TestCase):
    def test_honeypot_45_preserves_backend_high_severity_and_coverage_warning(self):
        markup = risk_summary(report(45, "High observed risk"))
        self.assertTrue(Elements(markup).with_class("risk-high"))
        self.assertIn('>High</span>', markup)
        self.assertIn("45/100", markup)
        self.assertIn("Assessment incomplete", markup)

    def test_complete_zero_has_low_badge_without_safety_claim(self):
        markup = risk_summary(report(level="No configured warnings (not verified safe)", complete=True))
        self.assertTrue(Elements(markup).with_class("risk-low"))
        self.assertIn('>Low</span>', markup)
        self.assertIn("0/100", markup)
        self.assertIn("does not certify safety", markup)

    def test_incomplete_zero_is_neutral_and_never_a_zero_or_low_score(self):
        markup = risk_summary(report())
        elements = Elements(markup)
        self.assertTrue(elements.with_class("risk-incomplete"))
        self.assertIn('>Incomplete</span>', markup)
        self.assertNotIn("0/100", markup)
        self.assertNotIn('>Low<', markup)
        self.assertEqual(elements.with_class("gauge-fill")[0]["opacity"], "0")
        self.assertEqual(elements.with_class("risk-ring")[0]["role"], "img")
        self.assertIn("unknown", elements.with_class("risk-ring")[0]["aria-label"])

    def test_critical_and_moderate_follow_backend_levels(self):
        for score, level, severity in [(75, "Critical observed risk", "critical"), (25, "Moderate observed risk", "moderate")]:
            self.assertTrue(Elements(risk_summary(report(score, level))).with_class("risk-" + severity))

    def test_ring_is_bounded_and_uses_normalized_circumference(self):
        for score, expected in [(-5, "0 100"), (45, "45 100"), (150, "100 100")]:
            elements = Elements(risk_summary(report(score, "Critical observed risk", complete=True)))
            self.assertEqual(elements.with_class("gauge-fill")[0]["stroke-dasharray"], expected)
            self.assertEqual(elements.with_class("gauge-fill")[0]["pathlength"], "100")
            self.assertEqual(elements.with_class("risk-ring")[0]["viewbox"], "0 0 200 200")

    def test_provider_findings_and_coverage_and_level_are_escaped(self):
        dangerous = '<img src=x onerror="alert(1)"> & other text'
        item = report(45, 'High observed risk" onmouseover="alert(1)', (dangerous,), coverage=dangerous)
        panel = warning_panel(item)
        summary = risk_summary(item)
        self.assertNotIn("<img", panel + summary)
        self.assertIn("&lt;img", panel + summary)
        self.assertIn("&amp; other text", panel + summary)
        badge = Elements(summary).with_class("risk-badge")[0]
        self.assertNotIn("onmouseover", badge)
        self.assertEqual(badge["title"], item.level)

    def test_known_warning_has_explanation_while_unknown_data_stays_neutral(self):
        findings = ("GoPlus flags possible honeypot behavior.",
                    "Unknown contract-security flags: is_mintable.",
                    "Only 3 of 5 signal categories have complete data. Missing data is not a safety indicator.")
        markup = warning_panel(report(45, "High observed risk", findings))
        elements = Elements(markup)
        self.assertEqual(len(elements.with_class("signal-warning")), 1)
        self.assertEqual(len(elements.with_class("coverage-note")), 2)
        self.assertIn("does not simulate a sale", markup)
        self.assertIn("What the scan found", markup)
        for finding in findings:
            self.assertIn(finding, markup)

    def test_no_warning_statement_remains_neutral(self):
        text = "No configured warning threshold was triggered in the available observations; this does not establish safety."
        elements = Elements(warning_panel(report(findings=(text,))))
        self.assertEqual(len(elements.with_class("no-warnings")), 1)
        self.assertFalse(elements.with_class("signal-warning"))

    def test_icons_are_decorative_and_only_fixed_names_are_supported(self):
        for name in ("shield", "liquidity", "volume", "price", "search", "history", "arrow", "check"):
            elements = Elements(icon(name))
            self.assertEqual(elements.items[0][1]["aria-hidden"], "true")
        with self.assertRaises(KeyError):
            icon('<script>')

    def test_history_unknowns_break_paths_without_becoming_zero_values(self):
        rows = [{"captured_at": "2026-10-15T12:00:00Z", "risk_score": 10},
                {"captured_at": "2026-10-15T12:01:00Z", "risk_score": None, "raw_risk_score": 0},
                {"captured_at": "2026-10-15T12:02:00Z", "risk_score": 30}]
        chart = scan_history_chart(rows, "risk_score", "Warning points", "#315e88")
        self.assertEqual([item["value"] for item in chart.data.values], [10, 30])
        self.assertNotEqual(chart.data.values[0]["segment"], chart.data.values[1]["segment"])
        self.assertEqual(chart.to_dict()["encoding"]["detail"]["field"], "segment")


if __name__ == "__main__":
    unittest.main()
