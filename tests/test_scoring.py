import unittest
from rugradar.market import TokenSnapshot
from rugradar.scoring import assess

ADDR = '0x' + 'a'*40


def example(**overrides):
    values = dict(address=ADDR, symbol='EXP', name='Example', dex='uniswap', pair_address='0x'+'b'*40,
                  price_usd=0.1, liquidity_usd=8000, volume_h24_usd=30000, change_h24_pct=-75,
                  buys_h24=5, sells_h24=100, captured_at='2026-10-15T00:00:00+00:00', pair_url='', price_is_available=True)
    values.update(overrides)
    return TokenSnapshot(**values)


class RiskTests(unittest.TestCase):
    def test_measurable_market_warnings(self):
        report = assess(example())
        self.assertEqual(report.score, 60)
        self.assertEqual(report.level, 'High observed risk')
        self.assertIn('not assessed', ' '.join(report.findings))

    def test_security_and_liquidity_drop(self):
        report = assess(example(), security={'is_honeypot':'1', 'is_mintable':'1'}, previous_liquidity=20000)
        self.assertEqual(report.score, 100)
        self.assertIn('GoPlus flags possible honeypot', ' '.join(report.findings))

    def test_unknown_does_not_mean_safe(self):
        report = assess(example(liquidity_usd=None, change_h24_pct=None, buys_h24=None, sells_h24=None))
        self.assertEqual(report.level, 'Insufficient data')
        self.assertIn('Missing data', ' '.join(report.findings))

    def test_low_score_still_carries_disclaimer(self):
        report = assess(example(liquidity_usd=200000, change_h24_pct=4, buys_h24=100, sells_h24=95))
        self.assertEqual(report.score, 0)
        self.assertIn('not verified safe', report.level)
