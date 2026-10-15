import tempfile
from pathlib import Path
import unittest
from rugradar.market import TokenSnapshot
from rugradar.scoring import assess
from rugradar.history import save_scan, latest_liquidity, token_history


class HistoryTests(unittest.TestCase):
    def test_scan_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'history.db'
            token = TokenSnapshot('0x'+'a'*40, 'ABC', 'Example', 'uniswap', '0x'+'b'*40,
                                  0.1, 15000.0, 100, 0, 1, 2, '2026-10-15T00:00:00+00:00', '', True)
            report = assess(token)
            self.assertIsNone(latest_liquidity(token.address, db))
            save_scan(token, report, db)
            self.assertEqual(latest_liquidity(token.address.upper().replace('0X','0x'), db), 15000.0)
            self.assertEqual(token_history(token.address, db_path=db)[0]['risk_score'], report.score)
