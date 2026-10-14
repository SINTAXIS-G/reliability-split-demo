"""
diagnose.py -- runnable implementation of the 5-step method from the
Walter-MIDE proposal: isolate a process-lifecycle defect from a
browser/delivery defect using evidence, not inference from symptoms.

Usage:
    python scanner.py &              # start the background process
    sleep 5
    python diagnose.py               # run the diagnosis against it

Each step prints the evidence it collected and the conclusion that
evidence licenses -- nothing is asserted without a value backing it.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import dashboard

DB_PATH = Path(__file__).parent / "scan_state.db"


def step1_confirm_process_completion() -> dict:
    """Ground truth, read directly from the store the scanner itself
    writes to -- bypasses the UI entirely, so it can't be lying."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT scan_count, last_result, updated_at FROM scan_state WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        raise SystemExit("No scan_state row found -- start scanner.py first.")
    truth = {"scan_count": row[0], "last_result": row[1], "updated_at": row[2]}
    print(f"[1] Ground truth from DB: scan_count={truth['scan_count']}, "
          f"updated_at={truth['updated_at']}")
    return truth


def step2_map_delivery_boundary() -> None:
    print("[2] UI read path: dashboard.read_scan_state() -- decorated with "
          "@st.cache_data, no ttl, no invalidation hook (dashboard.py:~24).")


def step3_compare_cached_view_to_truth(truth: dict) -> dict:
    cached_view = dashboard.read_scan_state()
    print(f"[3] Dashboard's cached view: scan_count={cached_view['scan_count']}, "
          f"updated_at={cached_view['updated_at']}")
    if cached_view["updated_at"] != truth["updated_at"]:
        print("    -> DIVERGENCE CONFIRMED: process has fresher data than the UI is showing.")
    else:
        print("    -> No divergence observed yet (cache may not have been primed before this run).")
    return cached_view


def step4_isolation_test(truth: dict) -> bool:
    """The decisive test: call the SAME query through the UNCACHED path.
    If it now matches ground truth, the defect is proven to live at the
    cache boundary -- not in the scanner process, which step 1 already
    showed is healthy."""
    uncached_view = dashboard.read_scan_state_uncached()
    print(f"[4] Uncached read (bypassing st.cache_data): scan_count="
          f"{uncached_view['scan_count']}, updated_at={uncached_view['updated_at']}")
    matches_truth = uncached_view["updated_at"] == truth["updated_at"]
    print(f"    -> Uncached read matches ground truth: {matches_truth}")
    return matches_truth


def step5_verdict(truth: dict, cached_view: dict, uncached_matches: bool) -> str:
    cache_is_stale = cached_view["updated_at"] != truth["updated_at"]
    if cache_is_stale and uncached_matches:
        verdict = (
            "DELIVERY_DEFECT_CONFIRMED: process lifecycle is healthy "
            "(ground truth is current); the cache boundary in dashboard.py "
            "is the fault. Targeted fix (cache ttl/invalidation), not "
            "architectural separation."
        )
    elif not cache_is_stale:
        verdict = "NO_DEFECT_OBSERVED: cached view matches ground truth at time of check."
    else:
        verdict = (
            "INCONCLUSIVE: cache is stale AND the uncached path also "
            "disagrees with ground truth -- re-check step 1's assumptions "
            "before trusting this result."
        )
    print(f"[5] VERDICT: {verdict}")
    return verdict


def main() -> None:
    truth = step1_confirm_process_completion()
    step2_map_delivery_boundary()
    cached_view = step3_compare_cached_view_to_truth(truth)
    # give the scanner a chance to move forward so step 3's cached read
    # (primed on the OLD state) now visibly disagrees with fresh truth
    time.sleep(3)
    fresh_truth = step1_confirm_process_completion()
    uncached_matches = step4_isolation_test(fresh_truth)
    step5_verdict(fresh_truth, cached_view, uncached_matches)


if __name__ == "__main__":
    sys.exit(main())
