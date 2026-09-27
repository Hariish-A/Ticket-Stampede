# DECISIONS

**Built:** a seller (FastAPI + asyncpg on Postgres 16) that sells exactly N tickets, and an open-loop buyer that attacks it and checks the invariants against `/status` **and against its own ledger** of what each buyer was told. Every claim below links to a saved run in `results/`, and every number was measured on one laptop (8-core Ryzen 7 7435HS, Docker Desktop).

## 1. Architecture, and what was rejected
- **Postgres enforces the invariants, not the app.** `/reset` creates N ticket rows. There is a PK on `ticket_no` (I2), `UNIQUE(request_id)` (I3) and `UNIQUE(user_id)` (one per user, D3). No row N+1 exists (I1).
  - **A buy is:** a lookup, then **one** `UPDATE … WHERE ticket_no = (SELECT … FOR UPDATE SKIP LOCKED)`. On a `UniqueViolation` the seller looks up again and returns the winner's ticket.
  - **No explicit transaction.** The constraints, not a lock held across statements, stop double sales.
  - **`/status` is one statement,** so the count equals the list by construction (I4).
  - **Sellers are stateless,** so TF1 needed no lock between instances.
- **Rejected, with evidence** ([C2](results/20260924T085114Z-c2-summary.md)):
  - `SERIALIZABLE`+retry: the textbook answer. In a 5,000-ticket sale it made 24,927 retries and sold 1,472 tickets.
  - A single counter row: about 250 claims/s. [Proved to be](results/20260924T093944Z-hotrow-summary.md) a row lock held across the disk flush (`pg_test_fsync` about 372/s). With the flush off it sold everything in 3.8 s.
  - At the brief's 100 tickets all three are acceptable. I say so rather than oversell SKIP LOCKED.
- **Rejected without building:** Redis+Lua (durability needs `appendfsync always`, no constraints); Redis in front of Postgres (dual writes put I4 at risk); Django (the ORM hides the SQL that *is* the product); microservices.
- **Two traps in SKIP LOCKED, each reproduced by a test before it was fixed:**
  1. "No row" can mean "the last ticket is mid-claim and about to roll back". Fix: a blocking fallback before answering sold out.
  2. A duplicate losing the last ticket to *its own twin* was told "sold out" (1 of 30). Fix: look up again before 409.

## 2. Naive → caught → fixed (the brief's C1)

| same 51,000-request stampede | tickets issued (100 seats) | I1 | I2 | I3 | I4 | live audit |
|---|---|---|---|---|---|---|
| [naive](results/20260927T024021Z-c1-naive/report.md) (read, await, write) | **2,187** | FAIL | FAIL (all 100 numbers sold 2+ times) | FAIL (5 request_ids got 2 tickets) | FAIL (`sold=100`, 2,187 listed) | FAIL, 1,216 violations |
| [skiplocked](results/20260927T024124Z-c1-skiplocked/report.md) | 100 | PASS | PASS | PASS (1,050 repeats) | PASS | PASS, 0 / 474 snapshots |

Behind 3 instances the naive seller sold **8,580** tickets ([TF1](results/M8-tf1.md)), and the safe one still passes.

## 3. What was measured, and what it changed
- **Coordinated omission is real here.** For the same 10 s database stall, a closed-loop client reports p99 **65 ms**; our open-loop client reports **9.9 s**. The closed-loop client sent 0–3 req/s while the database was stuck ([M6](results/M6-slowdb.md)).
- **Bottleneck** ([M5](results/M5-bottleneck.md)): each seller process's single core, spent in the web stack. Postgres is idle (0.1–0.4 of 20 connections active).
  - The evidence: CPU, `pg_stat_activity`, Server-Timing, py-spy, and an **intervention**. The sold-out answer (99.8% of traffic) went from 4 queries to 1 (same-snapshot `NOT EXISTS` test), which moved the knee from **1,000 to 1,500 req/s**, and p99 at 1,000/s from **310 to 15 ms**.
- **Client ceiling** (TF4): 12.7k req/s with 4 processes against a zero-work target, far above any seller number. Every report prints client health (worker CPU, send lag).
- **The slow datastore** ([M6](results/M6-slowdb.md)): +3 s on every Postgres answer for 10 s, 15,000 tickets. The invariants hold.
  - **What broke was availability:** a retry storm kept load at ~2× capacity after the stall ended. The result was a metastable outage, **1,693 orphans** (sold, buyer never told) and 6,856 buyers never answered.
  - **A client retry budget** (over-budget retries *wait*, never drop) gave **0 / 0**.
  - **Seller fail-fast** (ASGI shed before FastAPI) kept the seller responsive. I expected shedding to be too expensive in Python; the measurement said otherwise.
- **D24, fail-fast on by default at 64 in flight per instance** ([evidence](results/D24-failfast.md)). At the burst it sheds ~2% with a definite "not bought, retry", and p99 goes 1,846 → 675 ms. In the stall, orphans go 1,693 → 29. A limit of 256 was dominated: it shed about as much and protected far less (192 orphans, and the sale did not finish).
- **Two kinds of 503.** `not_attempted` means nothing was sent, so the buyer definitely did not buy. `unknown` means maybe they did. `/buy` never answers 500, whatever the exception.

## 4. TF2, the one done properly: SIGKILL Postgres mid-sale ([M7](results/M7-killdb.md))
- **3 out of 3 runs:** every invariant holds, 15,000 confirmed = 15,000 in `/status`, **0 confirmed sales lost**, 0 orphans.
- **The kill lands mid-commit:** 15–32 in-flight purchases per run *had* committed (the same-request_id retry found them), and 125–336 had not.
- **The durability argument:** a 200 is sent only after the single-statement `UPDATE` returns, and with `synchronous_commit=on` that is after the WAL flush. Crash recovery replays it.
- **Control run** (`synchronous_commit=off`): it **lost 6 confirmed sales and resold the seats**. `/status` looked perfect and the live audit passed; only the buyer's ledger caught it. Without this run, "0 lost" would be an unfalsified claim.
- **The first kill trial found a bug:** asyncpg raised an exception type missing from my error list while releasing a broken connection. The 500s it produced left 2 buyers holding tickets they didn't know about.

## 5. How it was tested
- **The tester is tested.** 39 buyer unit tests plant each kind of violation (oversell, duplicate, replay double-issue, count mismatch, phantom, conflict leak, false sold-out) and require a FAIL.
- **Seller races against real Postgres.** 34 integration tests cover concurrent twins, the last-ticket twin race, a claim rolling back under SKIP LOCKED, and conflicts, each × 3 strategies. Removing the SKIP LOCKED fallback makes 2 of them fail (mutation check).
- **End-to-end:** 51k-request stampedes, a live auditor, the ledger reconciliation, fault injection on the buyer's own clock, and control runs that must fail. **Discarded runs are kept with reasons** (`results/discarded/`): a run against the wrong seller, a cold-start sweep, a "sync off" run that was really on, order-confounded comparisons, a host suspend, and verifier bugs.

## 6. Where it breaks (known, measured where possible)
- **One laptop.** 3 instances scale about **1.3×**: imbalance and connection churn were ruled out, and host contention was measured (+25% seller CPU per request when the client uses more cores). The client shares the machine.
- **Crash safety, not power-loss durability:** `docker kill` is a process crash.
- **Single Postgres, single nginx:** no failover. Asynchronous replication would bring back the control run's losses.
- **Orphans are recovered only if the buyer retries** with the same request_id. A buyer who gives up never learns they own a ticket.
- **user_id and `/reset` are unauthenticated.** Resetting during live traffic can give a spurious sold-out.
- **The client reuses keep-alive connections,** so the seller's job is easier than 50k real connections would make it.
- **Cold start:** p99 is about 180–290 ms for the first seconds after a restart.
- **Static admission limit (64):** a compromise between the burst and a stall, tuned on this machine.

## 7. With two more weeks
1. Separate hosts for the client, sellers and database, for honest scaling curves.
2. An adaptive (latency-based) admission limit instead of a static one.
3. A "my tickets" lookup by user_id, so orphans resolve without retries.
4. Synchronous replication with a failover drill, the TF2 test extended to node loss.
5. TF3 (waitlist with 30 s holds), now that the state machine can build on the claim path.
6. A power-loss test on real hardware.

_Time: ~15–16 h of the 12–15 h budget. What is missing is listed above, not hidden. Process: Plan.md (decisions D1–D28), Progress.md, logs/._
