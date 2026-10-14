"""
scanner.py -- a process-owned background worker.

Simulates the class of system described in the Walter-MIDE reliability
engagement: a long-running Python process that performs real work on its
own schedule, independent of any UI, and persists its results to a shared
store (SQLite here) with a real completion timestamp.

This process deliberately knows nothing about Streamlit, caching, or the
browser. That separation is the whole point: if this process is healthy,
any staleness the user sees downstream is -- by construction -- NOT a
process-lifecycle defect, and the fault must be isolated somewhere in the
delivery path instead. diagnose.py proves that split with evidence.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "scan_state.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    scan_count INTEGER NOT NULL DEFAULT 0,
    last_result TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO scan_state (id, scan_count, last_result, updated_at) "
        "VALUES (1, 0, '', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    return conn


def run_one_scan(conn: sqlite3.Connection, scan_number: int) -> str:
    """Does the actual 'work'. Real timestamp, real row update -- the
    ground truth this whole demo is built to expose or confirm."""
    result = f"scan #{scan_number}: 0 anomalies, {scan_number * 3} symbols checked"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE scan_state SET scan_count = ?, last_result = ?, updated_at = ? WHERE id = 1",
        (scan_number, result, now),
    )
    conn.commit()
    return result


def scanner_loop(interval_seconds: float = 2.0, stop_event: threading.Event | None = None) -> None:
    """Owns its own process lifecycle end to end. Runs forever (or until
    stop_event is set) regardless of whether anything downstream is
    listening -- exactly the 'process-owned' framing from the client's
    question."""
    conn = _connect()
    scan_number = 0
    try:
        while stop_event is None or not stop_event.is_set():
            scan_number += 1
            run_one_scan(conn, scan_number)
            time.sleep(interval_seconds)
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Scanner starting. DB: {DB_PATH}")
    scanner_loop()
