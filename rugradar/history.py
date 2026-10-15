"""Local SQLite scan history. Cloud-hosted ephemeral filesystems are not durable storage."""
from __future__ import annotations
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from .market import TokenSnapshot
from .networks import address_key, get_network
from .scoring import RiskReport

DEFAULT_DB = Path(os.getenv("RUGRADAR_DB_PATH", "data/rugradar.db"))


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        # Serialize schema inspection and additive changes across app sessions.
        # Existing rows and their original scores are never rewritten.
        connection.execute("BEGIN IMMEDIATE")
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
        columns = {column["name"] for column in connection.execute("PRAGMA table_info(scans)")}
        additions = {
            "network": "TEXT NOT NULL DEFAULT 'base'",
            "coverage": "TEXT",
            "checked_count": "INTEGER",
            "possible_count": "INTEGER",
            "assessment_complete": "INTEGER",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE scans ADD COLUMN {name} {definition}")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_scans_token ON scans(contract_address, id)")
        connection.execute("""CREATE INDEX IF NOT EXISTS idx_scans_network_token
                              ON scans(network, contract_address, id)""")
        connection.execute("""CREATE INDEX IF NOT EXISTS idx_scans_network_evm_token
                              ON scans(network, lower(contract_address), id)""")
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        raise
    return connection


def latest_liquidity(
    address: str,
    db_path: str | Path = DEFAULT_DB,
    *,
    network: str = "base",
    pair_address: str | None = None,
) -> float | None:
    """Read a prior observation on one chain, optionally for one exact pool.

    Callers assessing liquidity changes should always pass the selected pool;
    omitting it preserves the original lookup behavior for existing clients.
    """
    selected = get_network(network)
    key = address_key(address, network)
    token_column = "lower(contract_address)" if selected.evm else "contract_address COLLATE BINARY"
    parameters: list = [network, key]
    pool_filter = ""
    if pair_address is not None:
        pool_column = "lower(pair_address)" if selected.evm else "pair_address COLLATE BINARY"
        pool_filter = f" AND {pool_column} = ?"
        parameters.append(pair_address.lower() if selected.evm else pair_address)
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            f"""SELECT liquidity_usd FROM scans WHERE network = ? AND {token_column} = ?
                {pool_filter} ORDER BY id DESC LIMIT 1""", parameters
        ).fetchone()
        return row["liquidity_usd"] if row is not None else None


def save_scan(snapshot: TokenSnapshot, report: RiskReport, db_path: str | Path = DEFAULT_DB) -> None:
    network = get_network(snapshot.network).key
    address_key(snapshot.address, network)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("""INSERT INTO scans
            (contract_address, symbol, pair_address, captured_at, liquidity_usd, price_usd,
             volume_h24_usd, risk_score, risk_level, findings_json, network, coverage,
             checked_count, possible_count, assessment_complete)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            snapshot.address, snapshot.symbol, snapshot.pair_address, snapshot.captured_at,
            snapshot.liquidity_usd, snapshot.price_usd, snapshot.volume_h24_usd,
            report.score, report.level, json.dumps(report.findings), network, report.coverage,
            report.checked_count, report.possible_count, int(report.is_complete),
        ))


def token_history(
    address: str,
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB,
    *,
    network: str = "base",
) -> list[dict]:
    selected = get_network(network)
    key = address_key(address, network)
    token_column = "lower(contract_address)" if selected.evm else "contract_address COLLATE BINARY"
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(f"""SELECT captured_at, liquidity_usd, price_usd, volume_h24_usd,
                                      risk_score, network, pair_address, coverage, checked_count,
                                      possible_count, assessment_complete
                               FROM scans WHERE network = ? AND {token_column} = ?
                               ORDER BY id DESC LIMIT ?""", (network, key, limit)).fetchall()
        result = []
        for row in reversed(rows):
            item = dict(row)
            item["raw_risk_score"] = item["risk_score"]
            # A zero with incomplete or unknown coverage is not a chartable
            # clean assessment. Keep the original score in storage and output.
            if item["risk_score"] == 0 and item["assessment_complete"] != 1:
                item["risk_score"] = None
            if item["assessment_complete"] is not None:
                item["assessment_complete"] = bool(item["assessment_complete"])
            result.append(item)
        return result
