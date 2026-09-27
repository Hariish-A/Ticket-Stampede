# D24: should seller fail-fast admission be on by default, and at what limit?

**Mechanism** (`seller/app/admission.py`): a pure ASGI middleware. When more than `MAX_INFLIGHT` `/buy` requests are inside one seller, the next one gets an immediate `503 not_attempted` (nothing was sent to the database, so the buyer definitely did not buy). This happens before FastAPI parses the body and before the request waits up to 1 s for a pool connection.

**The tension.** One static limit has to serve two opposite situations:
- **The opening burst** (the brief's 1,000 buyers at t=0). The seller drains them in under a second, so shedding them is pure loss.
- **A datastore stall.** Nothing drains, and everything beyond a small limit should be shed immediately (M6: without it, a 10 s stall became a metastable outage).

## Measurements (one seller, 2026-09-24 and 2026-09-27)

| limit | C1 burst (100 tickets, 51,000 requests): shed / p99 | 10 s stall mid-sale (15,000 tickets): orphans / never answered / sold out? |
|---|---|---|
| off (0) | 0 / **1,846 ms** ([run](20260927T024124Z-c1-skiplocked/report.md)) | **1,693 / 6,856** / yes, at 51.8 s ([run](20260924T102530Z-slowdb-baseline/report.md)) |
| **64** | 1,068 (2.1%) / **675 ms** ([run](20260927T024330Z-c1-skiplocked/report.md)) | **29 / 859** / yes, at 44.3 s ([run](20260924T102726Z-slowdb-failfast/report.md)) |
| 256 | 943 (1.8%) / 923 ms ([run](20260927T023714Z-c1-skiplocked/report.md)) | 192 / 2,018 / **no**: 14,319 of 15,000 sold ([run](20260927T023821Z-slowdb-failfast-256/report.md)) |

Every run passes every invariant; this is purely an availability decision.

## Decision: ON, `MAX_INFLIGHT=64` per instance (the compose default from 2026-09-27)
- **256 is dominated by 64.** At the burst both shed about the same (roughly the part of the 1,000 simultaneous arrivals that cannot be admitted at once), but 256 lets far more requests get stuck on a stalled database: 6.6× the orphans, and the sale did not finish.
- **64 vs off.** About 2% of the stampede (the burst itself) gets a definite "not bought, try again" instead of waiting up to ~2 s. In exchange: p99 at the burst drops 1,846 → 675 ms, and the seller survives a stall (orphans 1,693 → 29). A buyer told `not_attempted` loses nothing they had, and their retry is safe.
- **Not a final answer.** The right limit depends on capacity, and capacity depends on the machine (M5, M8). A static limit is a compromise; an adaptive one (derived from measured latency and throughput) is in "next two weeks".
- **Recorded runs before 2026-09-27 used `MAX_INFLIGHT=0`** unless a run says otherwise. `slowdb.sh` sets the limit explicitly per variant.
