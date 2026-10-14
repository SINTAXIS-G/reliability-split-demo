"""
diagnose.py -- runnable implementation of the 5-step method from the
Walter-MIDE proposal: isolate a process-lifecycle defect from a
browser/delivery defect using evidence, not inference from symptoms.

Usage:
    python scanner.py &              # start the background process
    sleep 5
    python diagnose.py               # run the diagnosis against it

Revision note: the first version of this script compared a cached read
captured BEFORE a wait against a database read taken AFTER it. That
establishes a time difference, not a caching defect on its own -- a
reviewer correctly flagged that a time-shifted comparison alone doesn't
isolate the fault. Fixed here: the decisive comparison now takes the
cached read, the uncached read, and ground truth ALL at the same
instant (step 4), after the process has been given time to advance in
the background. The wait only gets the system into a state where the
two paths *should* diverge if the defect is real; it is no longer part
of the evidence itself.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import dashboard

DB_PATH = Path(__file__).parent / "scan_state.db"


def read_ground_truth() -> dict:
    """Bypasses the UI and any cache entirely -- reads the scanner's own
    store directly. This is what step 1 and the final comparison in
    step 4 both call, so every ground-truth read in this script is the
    same query, run fresh, every time."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT scan_count, last_result, updated_at FROM scan_state WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        raise SystemExit("No scan_state row found -- start scanner.py first.")
    return {"scan_count": row[0], "last_result": row[1], "updated_at": row[2]}


def step1_confirm_process_completion() -> dict:
    truth = read_ground_truth()
    print(f"[1] Ground truth from DB: scan_count={truth['scan_count']}, "
          f"updated_at={truth['updated_at']}")
    return truth


def step2_map_delivery_boundary() -> None:
    print("[2] UI read path: dashboard.read_scan_state() -- decorated with "
          "@st.cache_data, no ttl, no invalidation hook (dashboard.py:~24).")


def step3_prime_the_cache(truth_at_prime_time: dict) -> dict:
    """First call to the cached function. st.cache_data has nothing to
    serve yet, so this read populates the cache with whatever is true
    right now -- and should match ground truth, since nothing stale
    exists yet."""
    primed = dashboard.read_scan_state()
    matches = primed["updated_at"] == truth_at_prime_time["updated_at"]
    print(f"[3] Cache primed with: scan_count={primed['scan_count']}, "
          f"updated_at={primed['updated_at']} (matches truth at prime time: {matches})")
    return primed


def step4_same_instant_comparison() -> tuple[dict, dict, dict]:
    """The decisive, non-time-confounded test. All three reads happen
    back to back, as close to the same instant as Python allows -- no
    comparison here spans a wait. cached_now uses the SAME cache key as
    step 3's priming call, so if nothing invalidated the cache, it will
    still return step 3's value even though truth_now has moved on."""
    cached_now = dashboard.read_scan_state()
    uncached_now = dashboard.read_scan_state_uncached()
    truth_now = read_ground_truth()
    print(f"[4] At the same instant -- cached: scan_count={cached_now['scan_count']}, "
          f"updated_at={cached_now['updated_at']}")
    print(f"    At the same instant -- uncached: scan_count={uncached_now['scan_count']}, "
          f"updated_at={uncached_now['updated_at']}")
    print(f"    At the same instant -- ground truth: scan_count={truth_now['scan_count']}, "
          f"updated_at={truth_now['updated_at']}")
    return cached_now, uncached_now, truth_now


def step5_verdict(cached_now: dict, uncached_now: dict, truth_now: dict) -> str:
    cache_matches_truth = cached_now["updated_at"] == truth_now["updated_at"]
    uncached_matches_truth = uncached_now["updated_at"] == truth_now["updated_at"]

    if (not cache_matches_truth) and uncached_matches_truth:
        verdict = (
            "DELIVERY_DEFECT_CONFIRMED: at the same instant, the uncached "
            "path matches ground truth and the cached path does not. "
            "Process lifecycle is healthy (ground truth is current); the "
            "cache boundary in dashboard.py is the fault, isolated without "
            "relying on timing alone. Targeted fix (cache ttl/invalidation), "
            "not architectural separation."
        )
    elif cache_matches_truth:
        verdict = "NO_DEFECT_OBSERVED: cached view matches ground truth at time of check."
    else:
        verdict = (
            "INCONCLUSIVE: neither cached nor uncached reads match ground "
            "truth at the same instant -- re-check step 1's assumptions "
            "before trusting this result."
        )
    print(f"[5] VERDICT: {verdict}")
    return verdict


def main() -> None:
    truth_at_start = step1_confirm_process_completion()
    step2_map_delivery_boundary()
    step3_prime_the_cache(truth_at_start)

    # Give the live scanner process time to complete more real scans in
    # the background. This wait is NOT the evidence -- it only gets the
    # system into a state where cached and uncached reads should diverge
    # if the defect is real. The actual proof is the same-instant triple
    # comparison in step 4, taken fresh after this wait.
    time.sleep(3)

    cached_now, uncached_now, truth_now = step4_same_instant_comparison()
    step5_verdict(cached_now, uncached_now, truth_now)


if __name__ == "__main__":
    sys.exit(main())
