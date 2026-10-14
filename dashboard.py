"""
dashboard.py -- the Streamlit UI that reads scanner.py's output.

Contains ONE real, reproducible bug, left in deliberately so diagnose.py
and tests/test_diagnosis.py have something true to find and prove:

    read_scan_state() is wrapped in st.cache_data with no ttl and no
    invalidation hook tied to scanner.py's writes. Streamlit will happily
    keep serving the first cached read forever, even while scan_state.db
    keeps getting fresher rows underneath it. The scanner process is
    completely healthy; the dashboard is lying about it.

This is the textbook Streamlit staleness defect: cache boundary != data
boundary. It has nothing to do with threads, the GIL, or WebSockets --
which is exactly why distinguishing it from THOSE failure classes (listed
as suspected risks in FINDINGS.md, not verified defects) requires the
evidence-based split in diagnose.py rather than a guess.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).parent / "scan_state.db"


@st.cache_data  # <-- FINDINGS.md #1: no ttl, no cache_data.clear() on write path
def read_scan_state() -> dict:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT scan_count, last_result, updated_at FROM scan_state WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        return {"scan_count": 0, "last_result": "", "updated_at": ""}
    return {"scan_count": row[0], "last_result": row[1], "updated_at": row[2]}


def read_scan_state_uncached() -> dict:
    """The fixed read path used by diagnose.py's isolation test --
    identical query, no cache boundary in front of it."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT scan_count, last_result, updated_at FROM scan_state WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        return {"scan_count": 0, "last_result": "", "updated_at": ""}
    return {"scan_count": row[0], "last_result": row[1], "updated_at": row[2]}


def main() -> None:
    st.title("Walter-MIDE reliability demo -- dashboard")
    state = read_scan_state()
    st.metric("Scans completed (as seen by dashboard)", state["scan_count"])
    st.write("Last result:", state["last_result"] or "(none yet)")
    st.write("Dashboard's view of updated_at:", state["updated_at"] or "(none yet)")
    st.caption(
        "This value is served from st.cache_data with no ttl. Compare it "
        "against `python diagnose.py` to see the gap against ground truth."
    )


if __name__ == "__main__":
    main()
