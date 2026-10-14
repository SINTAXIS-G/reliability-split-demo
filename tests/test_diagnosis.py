"""
Proves the diagnosis deterministically: starts the real scanner in a
background thread, lets it write several scans, and asserts that (a) the
cached dashboard view goes stale relative to ground truth, and (b) the
uncached path -- and only the uncached path -- tracks ground truth. That
pair of assertions IS the evidence that the defect sits at the cache
boundary, not in the scanner's process lifecycle.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scanner  # noqa: E402
import dashboard  # noqa: E402


def test_scanner_process_lifecycle_is_healthy(tmp_path, monkeypatch):
      db_path = tmp_path / "scan_state.db"
      monkeypatch.setattr(scanner, "DB_PATH", db_path)

    stop = threading.Event()
    t = threading.Thread(target=scanner.scanner_loop, args=(0.2, stop), daemon=True)
    t.start()
    time.sleep(1.0)
    stop.set()
    t.join(timeout=2)

    conn = scanner._connect()
    row = conn.execute("SELECT scan_count, updated_at FROM scan_state WHERE id = 1").fetchone()
    conn.close()

    assert row is not None
    assert row[0] >= 2, "scanner should have completed multiple scans on its own schedule"
    assert row[1], "scanner must stamp a real completion timestamp"


def test_dashboard_cache_goes_stale_while_process_stays_healthy(tmp_path, monkeypatch):
      db_path = tmp_path / "scan_state.db"
      monkeypatch.setattr(scanner, "DB_PATH", db_path)
      monkeypatch.setattr(dashboard, "DB_PATH", db_path)
      dashboard.read_scan_state.clear()  # fresh cache for this test

    conn = scanner._connect()
    scanner.run_one_scan(conn, 1)

    first_cached = dashboard.read_scan_state()
    first_truth = dashboard.read_scan_state_uncached()
    assert first_cached["updated_at"] == first_truth["updated_at"]

    # process does more real work -- ground truth moves forward
    scanner.run_one_scan(conn, 2)
    conn.close()

    stale_cached = dashboard.read_scan_state()  # SAME cache key -> still serves scan #1
    fresh_truth = dashboard.read_scan_state_uncached()

    assert fresh_truth["scan_count"] == 2, "ground truth must reflect the second scan"
    assert stale_cached["scan_count"] == 1, (
              "this is the defect: st.cache_data with no ttl keeps serving the "
              "first read even though the process already completed scan #2"
    )
    assert stale_cached["updated_at"] != fresh_truth["updated_at"], (
              "divergence between cached view and ground truth -- the evidence "
              "that isolates this as a delivery defect, not a process defect"
    )

    dashboard.read_scan_state.clear()
