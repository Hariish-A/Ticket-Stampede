# M5: how much load, and where is the bottleneck?

One seller instance: one uvicorn worker (one Python process), a pool of 20 connections, Postgres 16, on a 16-CPU Docker Desktop VM. All numbers below are from this machine and are machine-relative.

## Answer

| | |
|---|---|
| **Knee** (p99 turns up sharply) | **~1,500 req/s** after the M5 fix (~1,000 req/s before it) |
| **Ceiling** (throughput stops rising) | **~1,400–1,500 req/s** handled (~1,100–1,200 before) |
| **Bottleneck** | **The seller process's single CPU core.** It is spent in the Python HTTP/framework stack per request. Postgres is not the limit on the path that carries 99.8% of the traffic. |
| **Invariants** | PASS at every rate, including far past saturation. Overload produces 503 "unknown", never an oversell. |

## Evidence: four independent sources, plus an intervention

Sweeps: [before](20260924T091530Z-sweep/summary.md), [after](20260924T092512Z-sweep/summary.md) (steady open-loop, 15 s per step, warm-up discarded).

1. **Container CPU (`docker stats`).** At and past the knee, the seller runs at 85–96% of one core (bursts over 100% from the C side of uvloop/asyncpg). Postgres sits at 30–50% of *one* core, out of 16 available.
2. **Postgres itself (`pg_stat_activity`, sampled every ~0.3 s).** On average **0.1–0.4 of the 20 pool connections are active** at any rate. The rest are idle and waiting for the application (`ClientRead`). The database is waiting on us, not the other way round.
3. **Server-Timing (per request, from the seller).** At 2,000 offered req/s, the allocator's queries take p50 4 ms / p99 61 ms. Time **outside the handler** (HTTP parsing and queueing for the event loop) is p99 **10.2 s**. Requests wait for the one busy Python thread, not for the database. The pool waits (acquire p99 ≈ 1 s, the timeout) are a knock-on effect: a starved event loop keeps connections checked out longer.
4. **py-spy profile** ([2,000/s, before](20260924T091354Z-profile-skiplocked-2000/summary.md)): Python-level time is spread across the web stack (FastAPI/Starlette/Pydantic 49% inclusive, uvicorn 69% inclusive). asyncpg is 18% and our code 14%. No single hot function stands out.
5. **Intervention (the strongest evidence).** If per-request CPU is the limit, cutting per-request work must move the knee. The M4 profile showed every sold-out answer cost 4 queries. M5 answers it in 1: the lookup also tests for unsold tickets, in the same snapshot.

   | | before (4 queries) | after (1 query) |
   |---|---|---|
   | p99 at 1,000 req/s | 310 ms | **15 ms** |
   | seller CPU at 1,000 req/s | 85% | **68%** |
   | allocator time p50 | 1.8 ms | **0.4 ms** |
   | knee | ~1,000 | **~1,500** |
   | saturated throughput | ~1,100–1,200 | **~1,400–1,500** (+30%) |

   The bottleneck stayed where it was (seller CPU, Postgres idle). Only its height changed, which is what a CPU-bound process predicts.

**What we could not see:** a large share of py-spy samples land in uvloop's C event loop (`asyncio/runners.py:run`), where the Python-level profiler is blind. `py-spy --native` fails on this stack (`Failed to merge native and python frames`). So the split *inside* the event loop (syscalls, libuv, httptools parsing) is not measured. The conclusion does not depend on it: sources 1–3 and 5 all point at the process, not at what inside it.

## The claim path: a second bottleneck, for hot-row designs only

The sweep measures the sold-out path. For the path that actually *sells* tickets, [hot-row experiment](20260924T093944Z-hotrow-summary.md) (5,000 tickets):

| | tickets sold | 503s | p50 |
|---|---|---|---|
| counter, commit flush on (real) | 4,882 / 5,000, never sold out | 16,062 | 1,008 ms |
| counter, flush **off** (experiment) | all by 3.8 s | 568 | 2.5 ms |
| skiplocked, flush on (real) | all by 5.2 s | 2,357 | 2.5 ms |
| skiplocked, flush off (experiment) | all by 4.7 s | 1,839 | 2.3 ms |

`pg_test_fsync` on this disk: **~372 fdatasync/s (2.7 ms each)**. The counter design holds its one row lock across that flush, so claims are serialised at the disk's flush rate and cannot share one (no group commit). The measured ceiling is ~250 claims/s. skiplocked holds a different row per buyer, so concurrent commits share flushes, and removing the flush barely changes it. This confirms the M1/M4 hypothesis by intervention, not by correlation. (`synchronous_commit=off` is not durable; it was an experiment and has been restored.)

## Is the client the limit? No.
- Client ceiling ([calibration](20260924T083858Z-calibrate/report.md)): about 12.7k req/s with 4 processes, against a seller ceiling of about 1.5k.
- In the sweep, client send lag p99 is ≤ 12.6 ms up to 2,000 offered req/s.
- From 2,500 up, lag rises to seconds. That is the client's per-process in-flight cap binding *because the seller is saturated* (10 s responses × offered rate > the cap). It is reported, not hidden, and it lies beyond the knee.

## Buyer inside the compose network vs through the host port (D10)
[3 alternating rounds](20260924T094212Z-d10-summary.md) at 800 req/s: direct p50 1.9 ms / p99 5.2–5.9 ms; through Docker Desktop's port forwarding p50 2.9–3.1 ms / p99 6.6–9.5 ms. The forwarding adds about 1 ms; D10 holds, and the effect is small at this rate. (The first attempt, one run each with direct always first, reported direct p99 280 ms. That was a cold start after the seller was recreated. See below and `discarded/README.md`.)

## Found along the way
- **Cold start.** A freshly (re)started seller has p99 ~180–290 ms for its first seconds: the pool grows from 5 to 20 connections, and statement caches are cold. It matters after every deploy or restart (M7 kills and restarts things). Remedy, not yet applied: `POOL_MIN=POOL_MAX` plus a warm-up before taking traffic.
- **Measurement mistakes caught, runs discarded** (`discarded/README.md`): a sweep contaminated by the cold start; a hot-row "off" run that was really "on" (ALTER SYSTEM is outranked by the command-line flag; caught because the script prints the live setting); a D10 comparison confounded by run order.

## What would move the knee next
The limit is one Python process per instance, so the next step is **more processes**: 3 instances behind nginx (M8), or more uvicorn workers. We predict near-linear gains until Postgres CPU or the pool becomes visible in the same evidence (active connections, waits). M8 will measure it rather than assume it. The M9 in-memory sold-out cache would remove the remaining query on the hot path, but it attacks the smaller part of the cost: after M5 the allocator is 0.4 ms of a ~2.4 ms p50.
