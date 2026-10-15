"""Local SQLite scan history. Cloud-hosted ephemeral filesystems are not durable storage."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
from .market import TokenSnapshot
from .scoring import RiskReport

DEFAULT_DB = Path(os.getenv("RUGRADAR_DB_PATH", "data/rugradar.db"))


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_address TEXT NOT NULL,
        symbol TEXT NOT NULL,
        pair_address TEXT,
        captured_at TEXT NOT NULL,
        liquidity_usd REAL,
        price_usd REAL,
        volume_h24_usd REAL,
        risk_score INTEGER NOT NULL,
        risk_level TEXT NOT NULL,
        findings_json TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_scans_token ON scans(contract_address, id)")
    return connection


def latest_liquidity(address: str, db_path: str | Path = DEFAULT_DB) -> float | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT liquidity_usd FROM scans WHERE lower(contract_address) = lower(?) ORDER BY id DESC LIMIT 1", (address,)
        ).fetchone()
        return row["liquidity_usd"] if row is not None else None


def save_scan(snapshot: TokenSnapshot, report: RiskReport, db_path: str | Path = DEFAULT_DB) -> None:
    with _connect(db_path) as conn:
        conn.execute("""INSERT INTO scans
            (contract_address, symbol, pair_address, captured_at, liquidity_usd, price_usd,
             volume_h24_usd, risk_score, risk_level, findings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            snapshot.address, snapshot.symbol, snapshot.pair_address, snapshot.captured_at,
            snapshot.liquidity_usd, snapshot.price_usd, snapshot.volume_h24_usd,
            report.score, report.level, json.dumps(report.findings),
        ))


def token_history(address: str, limit: int = 100, db_path: str | Path = DEFAULT_DB) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute("""SELECT captured_at, liquidity_usd, price_usd, volume_h24_usd, risk_score
                               FROM scans WHERE lower(contract_address) = lower(?)
                               ORDER BY id DESC LIMIT ?""", (address, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]
