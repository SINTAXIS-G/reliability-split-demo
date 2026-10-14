# FINDINGS.md

A runnable demonstration of the report format described in the Walter-MIDE
engagement: verified defects separated from suspected risks, each with
file/line references and evidence, a prioritized remediation plan, and an
explicit recommendation on targeted repair vs. architectural separation.

Reproduce: `python scanner.py &` then `python diagnose.py`, or `pytest tests/ -v`.

---

## Verified Defects

### V1 — Dashboard cache boundary does not track process state
**File:** `dashboard.py:24` (`@st.cache_data` on `read_scan_state`, no `ttl`, no
`.clear()` call anywhere on the scanner's write path in `scanner.py`)

**Evidence:** `tests/test_diagnosis.py::test_dashboard_cache_goes_stale_while_process_stays_healthy`
(passing, deterministic) proves: after the scanner completes a second scan
(`scanner.run_one_scan`, ground truth `scan_count == 2`), the cached read
still returns `scan_count == 1` from before the second scan — while the
uncached read of the identical query returns the correct, current value.
Live run of `diagnose.py` against the real background process reproduces
the same split (see run log: step 1 ground truth vs. step 3 cached view).

**Root cause:** `st.cache_data`'s default behavior is to memoize by
function signature with no expiry. The scanner process has no awareness
of the UI's cache at all — correctly, by design — but nothing on the
write path invalidates it either. Cache boundary and data boundary are
two different things here, and nothing keeps them in sync.

**Classification:** process lifecycle is healthy (ground truth timestamps
advance correctly on schedule, confirmed independently of the UI in step
1). This is a delivery-layer defect, not a process-lifecycle defect.

---

## Suspected Risks (not verified — require further investigation)

### S1 — Voice/audio alert delivery under autoplay policy
Browsers reject or silently drop `HTMLAudioElement.play()` calls that
aren't tied to a direct user gesture, depending on autoplay policy. A
background-triggered alert (scanner → UI → audio) is exactly the shape
that can hit this. **Not verified here** because it requires a real
browser session to reproduce — a headless Python test can't observe an
autoplay rejection. To confirm: trigger the alert path and inspect the
browser console for a rejected `play()` promise, or log
`audio.play().catch(...)` explicitly (if that `.catch()` doesn't exist
yet in the real codebase, that absence is itself worth flagging).

### S2 — `st.session_state` writes from background threads
If the real system updates `st.session_state` directly from a scanner
thread (rather than reading from an external store as this demo does),
that write has no `ScriptRunContext` and is a TOCTOU hazard against the
next script rerun — state can be read stale, overwritten non-atomically,
or dropped with no exception. **Not verified** against the actual
codebase; flagged because the client's symptom description is consistent
with it. To confirm: grep the real app for any `st.session_state` mutation
that occurs outside the main script thread.

### S3 — Streamlit's own browser↔server WebSocket vs. the external market-data WebSocket/MQTT connection
These are two independent connections with independent failure modes
(idle-timeout/reverse-proxy drops on Streamlit's internal channel vs.
reconnect/backoff/QoS semantics on the market-data feed). A report that
doesn't separate "stale session" caused by one from "missed update"
caused by the other will misattribute the fix. **Not verified** —
flagged as a classification risk for the real investigation, not a
confirmed defect in this demo (which has no external data feed).

---

## Prioritized Remediation Plan

| Priority | Item | Effort | Fix type |
|---|---|---|---|
| P0 | V1 — add `ttl` to `read_scan_state`'s cache, or call `.clear()` on the scanner's write path | Hours | Targeted |
| P1 | S1 — reproduce under a real browser session; add explicit `.catch()` logging on the alert's `play()` call | Hours–1 day | Targeted |
| P2 | S2 — audit every `st.session_state` mutation for thread origin | 1–2 days | Targeted, pending audit |
| P3 | S3 — instrument both WebSocket layers independently (separate log namespaces) before attempting any fix | 1 day | Diagnostic, not a fix |

## Recommendation

**Targeted repairs, not architectural separation.** Every defect found or
flagged here is a boundary problem (cache invalidation, thread-safety of
a specific write, ambiguity between two connections) — not evidence that
Streamlit's execution model is structurally incompatible with this
workload. Separating components out of Streamlit would be justified if
P2 or P3 turned up a hazard that can't be fixed within Streamlit's model
at all; nothing found so far meets that bar.
