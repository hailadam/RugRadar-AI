"""History migrations and chain/pool isolation using temporary databases only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rugradar.history import latest_liquidity, save_scan, token_history
from rugradar.market import TokenSnapshot
from rugradar.scoring import RiskReport


ADDRESS = "0x" + "a" * 40
POOL = "0x" + "b" * 40
OTHER_POOL = "0x" + "c" * 40


def snapshot(address=ADDRESS, network="base", pool=POOL, liquidity=15000.0):
    return TokenSnapshot(
        address, "ABC", "Example", "uniswap", pool, 0.1, liquidity, 100,
        0, 1, 2, "2026-10-15T00:00:00+00:00", "", True, network=network,
    )


def report(score=15, checked=3, possible=5):
    return RiskReport(score, "Observed risk", ("Example finding",),
                      f"{checked}/{possible} categories", checked, possible)


class MultichainHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "history.db"

    def make_legacy_database(self, score=0):
        with sqlite3.connect(self.db) as connection:
            connection.execute("""CREATE TABLE scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT, contract_address TEXT NOT NULL,
                symbol TEXT NOT NULL, pair_address TEXT, captured_at TEXT NOT NULL,
                liquidity_usd REAL, price_usd REAL, volume_h24_usd REAL,
                risk_score INTEGER NOT NULL, risk_level TEXT NOT NULL,
                findings_json TEXT NOT NULL)""")
            values = (ADDRESS.upper().replace("0X", "0x"), "LEGACY", POOL,
                      "2026-01-01T00:00:00+00:00", 25000.0, 0.25, 1000.0,
                      score, "Original level", json.dumps(["Original finding"]))
            connection.execute("INSERT INTO scans VALUES (9, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        return values

    def test_additive_migration_preserves_legacy_values_and_is_repeatable(self):
        original = self.make_legacy_database()
        for _ in range(3):
            self.assertEqual(latest_liquidity(ADDRESS, self.db), 25000.0)
            rows = token_history(ADDRESS, db_path=self.db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["network"], "base")
            self.assertIsNone(rows[0]["risk_score"])
            self.assertEqual(rows[0]["raw_risk_score"], 0)
            self.assertIsNone(rows[0]["assessment_complete"])
        with sqlite3.connect(self.db) as connection:
            stored = connection.execute("""SELECT contract_address, symbol, pair_address,
                captured_at, liquidity_usd, price_usd, volume_h24_usd, risk_score,
                risk_level, findings_json FROM scans WHERE id = 9""").fetchone()
            self.assertEqual(stored, original)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scans").fetchone()[0], 1)

    def test_new_scans_append_after_migrated_rows(self):
        self.make_legacy_database(score=25)
        save_scan(snapshot(liquidity=20000), report(), self.db)
        self.assertEqual(latest_liquidity(ADDRESS, self.db), 20000)
        rows = token_history(ADDRESS, db_path=self.db)
        self.assertEqual([row["risk_score"] for row in rows], [25, 15])
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT id FROM scans ORDER BY id").fetchall(), [(9,), (10,)])

    def test_chain_and_pool_isolation_with_evm_case_folding(self):
        save_scan(snapshot(liquidity=10000), report(), self.db)
        save_scan(snapshot(network="ethereum", liquidity=90000), report(), self.db)
        save_scan(snapshot(pool=OTHER_POOL, liquidity=50000), report(), self.db)
        mixed_case_address = ADDRESS.upper().replace("0X", "0x")
        mixed_case_pool = POOL.upper().replace("0X", "0x")
        self.assertEqual(latest_liquidity(mixed_case_address, self.db, pair_address=mixed_case_pool), 10000)
        self.assertEqual(latest_liquidity(ADDRESS, self.db, pair_address=OTHER_POOL), 50000)
        self.assertEqual(latest_liquidity(ADDRESS, self.db, network="ethereum", pair_address=POOL), 90000)
        self.assertIsNone(latest_liquidity(ADDRESS, self.db, network="ethereum", pair_address=OTHER_POOL))
        self.assertIsNone(latest_liquidity(ADDRESS, self.db, network="arbitrum"))
        self.assertEqual(len(token_history(mixed_case_address, db_path=self.db)), 2)
        self.assertEqual(len(token_history(ADDRESS, db_path=self.db, network="ethereum")), 1)

    def test_solana_token_and_pool_keys_are_case_sensitive(self):
        first = "So11111111111111111111111111111111111111112"
        second = "so11111111111111111111111111111111111111112"
        pool = "So11111111111111111111111111111111111111113"
        save_scan(snapshot(first, "solana", pool, 12000), report(), self.db)
        save_scan(snapshot(second, "solana", pool, 34000), report(), self.db)
        self.assertEqual(latest_liquidity(first, self.db, network="solana", pair_address=pool), 12000)
        self.assertEqual(latest_liquidity(second, self.db, network="solana", pair_address=pool), 34000)
        self.assertIsNone(latest_liquidity(first, self.db, network="solana", pair_address=pool.lower()))
        self.assertEqual(len(token_history(first, db_path=self.db, network="solana")), 1)

    def test_incomplete_zero_is_not_a_chartable_clean_result(self):
        save_scan(snapshot(), report(score=0, checked=0), self.db)
        save_scan(snapshot(), report(score=0, checked=3), self.db)
        save_scan(snapshot(), report(score=0, checked=5), self.db)
        save_scan(snapshot(), report(score=30, checked=1), self.db)
        rows = token_history(ADDRESS, db_path=self.db)
        self.assertEqual([row["risk_score"] for row in rows], [None, None, 0, 30])
        self.assertEqual([row["raw_risk_score"] for row in rows], [0, 0, 0, 30])
        self.assertEqual([row["assessment_complete"] for row in rows], [False, False, True, False])
        self.assertEqual(rows[1]["coverage"], "3/5 categories")
        self.assertEqual(rows[1]["checked_count"], 3)
        self.assertEqual(rows[1]["possible_count"], 5)
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT risk_score FROM scans ORDER BY id").fetchall(),
                             [(0,), (0,), (0,), (30,)])

    def test_concurrent_migration_and_writes_preserve_all_scans(self):
        self.make_legacy_database()

        def write_scan(index):
            save_scan(replace(snapshot(), liquidity_usd=10000 + index), report(), self.db)
            return len(token_history(ADDRESS, db_path=self.db))

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(write_scan, range(8)))
        self.assertEqual(len(token_history(ADDRESS, db_path=self.db)), 9)
        self.assertTrue(all(count >= 2 for count in results))


if __name__ == "__main__":
    unittest.main()
