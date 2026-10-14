# reliability-split-demo

A small, self-contained, runnable demonstration of one specific diagnostic
method: proving whether a background process's work failed to complete,
or completed correctly but got lost somewhere on the way to the UI.

Built directly in response to this question — *"given a process-owned
Python scanner that completes scans while the dashboard goes stale or
voice alerts fail, how would you distinguish a process-lifecycle defect
from a browser-delivery defect using actual code and runtime evidence?"*
— as the evidence for the answer, not just a description of it.

## What's here

- `scanner.py` — a background worker that owns its own lifecycle and
  writes real, timestamped results to SQLite, independent of any UI.
- `dashboard.py` — a Streamlit app reading that state. Contains one real,
  left-in-on-purpose defect (`st.cache_data` with no `ttl`/invalidation).
- `diagnose.py` — runnable implementation of the 5-step evidence method:
  confirm process completion independently of the UI, map the delivery
  boundary, compare cached vs. ground truth, run the isolation test
  (uncached read), and print a verdict backed by the values collected.
- `tests/test_diagnosis.py` — deterministic, passing tests that prove the
  defect and the diagnosis, not just assert them in prose.
- `FINDINGS.md` — the actual deliverable format: verified defects
  separated from suspected risks, file/line references, a prioritized
  remediation plan, and a recommendation on targeted fix vs. architectural
  separation.

## Run it

```bash
pip install streamlit pytest
python scanner.py &          # background worker, writes to scan_state.db
sleep 5
python diagnose.py           # runs the 5-step method against it, prints the verdict
pytest tests/ -v              # deterministic proof of the same defect
```
