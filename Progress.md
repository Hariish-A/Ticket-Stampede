# Progress

> A running log that lets any AI agent continue where the last one stopped.
> Append new entries at the bottom of the log. Keep "Current state" and "Next up" current.

## Current state
- **Phase:** M6 is done (the datastore goes slow for 10 s: `results/M6-slowdb.md`). M7 is next, when the user says "start M7".
- **Runs?**
  - `./scripts/test.sh`: 36 buyer unit + 34 seller integration tests, all passing.
  - New: `./scripts/slowdb.sh` (5 variants).
- **Headline:** the invariants hold through the stall. The real damage is a retry storm: a metastable outage, 1,693 orphans, 6,856 buyers never answered. A client retry budget eliminates it; seller fail-fast keeps the seller responsive.
- **Repo:** https://github.com/Hariish-A/Ticket-Stampede (private), branch `main`.

## Next up
1. The user decides D24: turn seller fail-fast on by default, and at what limit? (It also sheds part of the brief's opening burst.)
2. M7: kill Postgres mid-sale and restart it (TF2). Use `--retry-unknown` plus `--retry-rate` in the buyer. Check that the postgres restart policy doesn't auto-restart a *killed* postgres (M3 note). Watch the cold start (M5).

## Known weaknesses / open issues
_(These feed into the "where it breaks" section of DECISIONS.md.)_
- The instances cache "sold out" in memory, and a /reset sent to one instance doesn't clear the others' caches unless we add invalidation (e.g. Postgres LISTEN/NOTIFY). This flaw is in the AI's own Session 2 caching suggestion.
- user_id isn't authenticated, so the one-ticket-per-user rule can be bypassed by making up new user_ids. /reset isn't authenticated either.
- The load client and the seller share one machine's CPU, so throughput numbers depend on the machine.
- A single Postgres node is a single point of failure; asynchronous replication would make failover lose confirmed sales.
- (M1 → fixed in M3) **The single-process buyer lagged during the opening burst** (send lag p99 71–98 ms, max 240–310 ms). With 4 processes: p99 about 12 ms, max 70–90 ms, workers at 12% CPU.
- (M3) **Client ceiling depends on the machine, and scaling is sub-linear**: 4.8k / 8.2k / 12.7k / 20.7k req/s at 1 / 2 / 4 / 8 processes, on a 16-CPU Docker Desktop VM shared with nginx and the seller. Every worker was at about 100% CPU and nginx peaked at 155%, so the limit is the client's Python. The stampede runs offer about 1k req/s, far below the ceiling.
- (M3) **The client reuses keep-alive connections; real buyers wouldn't.** 50k real users means 50k separate TCP connections and TLS handshakes. Our workers reuse pooled connections, which makes the seller's job easier than reality. Deliberate: one connection per request would exhaust the client's ephemeral ports (about 28k) and measure the client's connect cost instead.
- (M3) **The live auditor adds load**: about 10 `/status` requests/s on the seller during the sale. Small, but non-zero.
- (M1 → fixed in M6, D22) **A pool-acquire timeout answered 503 "unknown", but the outcome is actually known**: the request never reached the database, so nothing happened. M6 should separate "not attempted, safe to retry" from "unknown outcome".
- (M2) **The safe seller also saturates at the opening burst.** In the C1 skiplocked run, 1,479 of 51k requests got 503 (all `TimeoutError`: waiting more than 1 s for one of 20 pool connections). p99 was 1.5 s and max 2.4 s. No invariant was affected, because those requests never reached the database. M5 will find the bottleneck; candidates are single-process Python CPU, pool size, and the sold-out path's 4 queries (lookup, skip claim, blocking claim, re-lookup).
- (M2) **/reset during live traffic isn't safe for the epoch.** A buy whose statement snapshot predates a concurrent TRUNCATE can see an empty `tickets` table and answer a spurious "sold out" for the new epoch. U4 and U3 would flag it. Resetting mid-sale is outside the brief; not handled.
- (M6) **Result timestamps are Docker-VM time, not wall time.** The Docker Desktop (WSL2) VM clock drifted about 3 h behind the host, probably after host sleep. Folder names in `results/` use the VM clock. In-run measurements use a monotonic clock and are unaffected, unless the host suspends mid-run (that would show as a huge latency spike and client send lag in the report).
- (M6) **Retry storm → metastable failure.** Without a client retry budget, a 10 s datastore stall keeps one seller overloaded for 40 s+ after the stall ends (offered ~3k req/s vs ~1.5k capacity). Real browsers have no retry budget, which is why seller-side shedding (D24) matters.
- (M6) **Orphans need retries to be recovered.** Committed-but-unconfirmed tickets are only discovered when the buyer retries with the same request_id. A buyer who gives up keeps an orphan they don't know about (1,693 in the baseline). A real system would need a "my tickets" lookup, or notification by user_id.
- (M6) **The fail-fast limit (64) and the retry budget (200/s) are reasoned from M5's capacity, not swept.**
- (M5) **Cold start**: a freshly (re)started seller has p99 of about 180–290 ms for its first seconds (pool grows 5 → 20, cold caches). This matters after M7's restarts and any deploy. Remedy (not applied): `POOL_MIN=POOL_MAX` plus a warm-up before taking traffic.
- (M5) **The profiler can't see inside uvloop.** Much of the py-spy time lands in `asyncio/runners.py:run` (uvloop's C code), and `py-spy --native` fails on this stack ("Failed to merge native and python frames"). The bottleneck conclusion rests on the other evidence (CPU, pg_stat_activity, Server-Timing, the fast-path intervention).
- (M5) **One Python process per instance is the ceiling (~1.5k req/s).** The next lever is more processes (M8); the framework's per-request cost is the largest remaining share.
- (M4 → fixed in M5) **skiplocked's sold-out path did 4 queries**: lookup, SKIP LOCKED claim (empty), blocking claim (empty), re-lookup. In the brief run, all 50,079 sold-out requests took the blocking fallback, because after sell-out the fast path always finds nothing. 99.8% of traffic takes this path, so it's the first optimisation target in M5 (a cheaper definitive sold-out test, or the M9 cache).
- (M4) **Under sustained contention, counter and serializable turn into mass 503s.** Large sale: 16,260 (counter) and 19,533 (serializable) of 21k requests got "unknown", and neither sold out by the end of the run. Correct, but unusable.
- (M1 → supported by M4) **The naive seller handles only about 200–400 buys/s**. The counter strategy (the same single-row design, done safely) measured about 250 claims/s, which supports the hot-row hypothesis. Whether commit/fsync latency is the cause is still unproven (M5).
- (M1, original note) There were 6–8k 503s per run, and p90 latency was about 1 s, which matches the 1 s acquire timeout. Hypothesis: every buy does `UPDATE sale` on the single row, and each of those commits waits for a WAL fsync while holding the row lock. So buys queue behind fsync latency (the "hot row" problem). The C2 `counter` strategy would have the same problem. Unverified until measured.

## Open questions for the user
- D24: enable seller fail-fast admission by default? The measured trade-off: stall resilience (orphans 1,693 → 29, recovery right after the stall) vs shedding part of the brief's 1,000-request opening burst at a limit of 64. Options: keep off; on with a higher limit (e.g. 256, not measured); or shed at nginx instead (M8).

---

## Log

### 2026-09-24 — Session 1 (Claude Code): project setup
- Read the hackathon ground rules and evaluation criteria.
- Created `Instructions.md` (persistent rules), `Plan.md` (the game plan, still a template), `Progress.md` (this file), and an empty `logs/` directory.
- The user asked for logging in `/logs` to start from the next session.
- No code written yet.

### 2026-09-24 — Session 2 (Claude Code): problem statement and architecture Q&A
- Recorded the problem statement in `Plan.md` §1.
- Answered the user's 10 architecture questions: repo layout, FastAPI fit, functional/non-functional requirements, load balancing, HA, fault tolerance, SQL vs NoSQL, caching, rate limiting, idempotency. The full answers are in the session transcript under `logs/claude-code/`.
- Main findings, to carry into the plan:
  - **Verification trusts the system under test.** Checking invariants only through /status means asking the seller to grade itself. The buyer must reconcile its own ledger of confirmed responses against /status.
  - **The naive in-memory FastAPI version may not race** on a single asyncio worker (there's no `await` between read and write). The naive version must read-then-write against the datastore, or run multi-worker, for the oversell to show.
  - **After the 100 sales, the table is immutable.** About 99.8% of traffic is sold-out or replays, so each instance can cache the ≤100-entry winners map, keyed by sale epoch, and answer those requests from memory.
  - **/reset racing with in-flight buys:** a buy for the old sale could land in the new one. We need a sale epoch/generation id.
  - **A timeout is an unknown outcome.** It must never be turned into a "sold out" answer. Return 503 with "retry with the same request_id".
  - **Async Redis replication, or Redis without fsync,** loses confirmed sales on failover or kill, which leads to overselling and duplicate ticket numbers.
- No code written. Decisions are pending (see Open questions).

### 2026-09-24 — Session 3 (Claude Code): decisions and differentiators
- User decisions: Postgres, one ticket per user_id, TF2 deep + TF1, buyer in Python multiprocess. Recorded as D1–D5 in `Plan.md`.
- Ranked the user's 10 questions by relevance to the brief. Rate limiting and multi-node HA are mostly dropped; only admission control and the "replication loses confirmed sales" point are kept.
- Recommended FastAPI + asyncpg over Django (D6, pending).
- Proposed differentiators:
  - latency measured on a fixed arrival schedule instead of a fixed number of concurrent requests (avoids "coordinated omission");
  - the buyer's own ledger reconciled against /status, including orphaned tickets;
  - a live invariant auditor that checks while the sale runs;
  - calibrating the client's own ceiling;
  - measured comparisons: SERIALIZABLE vs counter row vs SKIP LOCKED; unbounded vs capped concurrency during the slowdown.
- Named weaknesses, including a flaw in the AI's own caching suggestion (cross-instance invalidation on reset).

### 2026-09-24 — Session 3 (continued): planning
- User confirmed: FastAPI (D6); differentiators A1–A4 and C1, C2, C4; D7 (200 with the existing ticket); build the Critical/High/Medium questions (D8).
- Mid-planning, the user asked for milestones that each end in something that runs (D9). Rewrote §6 as M1–M10, each with a Build list, a demo command and acceptance criteria.
- Wrote `Plan.md` §2–5: scope, architecture, data model, the /buy flow, buyer design, test strategy.
- Design details added during planning:
  - With SKIP LOCKED, "no row returned" doesn't prove sold out: the locked rows may roll back. So we confirm without skipping locked rows before answering 409.
  - A UniqueViolation from a duplicate at the same instant means: roll back, then look up the existing sale again.
  - Every response carries the epoch, so the buyer can spot a reset during its run.
  - Server-Timing is used as bottleneck evidence.
- Environment: Docker 27.3.1 and Compose v2.30 are installed, but Docker Desktop was not running. Python 3.12.0; 16 CPUs.
- A first attempt to update Plan.md through a bash heredoc failed on a quoting error; rewrote it with the Write tool.

### 2026-09-24 — Session 3 (continued): deployment Q&A
- User asked whether anything is running locally, and which free platform could host this if deployment were requested.
- Answer: nothing is built or running yet; the plan is local docker compose.
- Recommendation if deployment is needed: an Oracle Cloud Always Free Arm VM running the same compose file, which keeps every experiment working. GitHub Codespaces is the no-card alternative for reproducing it. A PaaS combination (e.g. Render + Neon/Supabase) works only as a correctness demo.
- Differences a PaaS introduces:
  - no way to kill the database or inject latency (TF2 and slowdown experiments impossible);
  - poolers in transaction mode break asyncpg's prepared statements and LISTEN/NOTIFY;
  - low connection limits;
  - app-to-DB network latency lengthens how long row locks are held;
  - tiny CPU;
  - free services that sleep and cold-start;
  - platform DDoS/rate limits;
  - the buyer running over the internet measures the internet, not the seller.
- Portability items to build in now: everything configured through environment variables (DATABASE_URL, pool size, statement_cache_size); correctness must never depend on LISTEN/NOTIFY. Candidate for M5: do the lookup and the claim in one database round trip.

### 2026-09-24 — Session 3 (continued): AWS free tier Q&A
- User asked whether AWS free tier is feasible and what would change.
- Checked the current free tier: accounts created after 2025-07-15 get $100 credit plus up to $100 more, for 6 months or until spent. t3.micro and RDS micro usage draws down those credits. Older accounts stay on the legacy 12-month tier.
- Recommendation:
  - Keep local compose as the submission.
  - Optional AWS step: run the same compose on EC2 (Linux, with self-managed Postgres so TF2's kill still works).
  - Put the buyer on a separate EC2 instance in the same AZ, so client and seller don't share CPU (stronger TF4 proof).
  - Use credits for a short benchmark window on non-burstable instances.
- Rejected on AWS:
  - Lambda: account concurrency limits, connection storms, RDS Proxy not free.
  - RDS for TF2: a reboot is not a kill -9.
  - Relying on t3.micro for load numbers: CPU credit throttling and 1 GiB RAM.
- Traps named: burstable CPU credits distort results in the middle of a test; /reset is exposed publicly (restrict with a security group or an admin token); public IPv4 charges; EBS fsync latency differs from local.
- Awaiting the user's decision on whether to add an optional M11 (AWS).

### 2026-09-24 — Session 4 (Claude Code): M1, the naive seller gets caught
- User: skip deployment for now. Standing rule added to `Instructions.md` §3a: "start X" means developed, tested, a working deliverable, and committed/pushed to the private GitHub repo.
- Built:
  - `seller/`: FastAPI + asyncpg. `/reset` bumps the epoch and TRUNCATEs. `/buy` and `/status` dispatch to the allocator chosen by `ALLOCATOR`; M1 has `naive` only (read counter, await, INSERT, write back the counter; no transaction or constraints). Timeouts and DB errors return 503 `unknown`. Schema is applied on startup under an advisory lock.
  - `buyer/`: `schedule.py` builds an open-loop schedule (burst at t=0, then a fixed rate), with duplicate kinds dup_concurrent, dup_sequential, replay_after_sellout, same_user_new_rid and rid_conflict. `runner.py` uses aiohttp with no connection limit, sends each request at its scheduled time, and records one Attempt per request. `verify.py` checks I1–I4 against /status and the buyer's own ledger, plus U1–U4 and orphans (A2). `stats.py` covers throughput, latency from the scheduled send, service time and client send lag. `report.py` writes md + json + a ledger.
  - `docker-compose.yml` (postgres, seller1, buyer under the `tools` profile), `scripts/test.sh`, `scripts/naive.sh`, README.
- Tests: 17 unit tests pass, including a planted-defect test for every check ("testing the tester").
- Demo results (`results/*naive-seed{1,2,3}`), 50k buyers + 1,090 duplicates, burst 1000, then 1000/s:
  - 3 out of 3 runs FAIL I1, I2, I3, I4, U1 and U2;
  - 1,811–2,012 tickets issued for 100 seats;
  - `/status` says `sold=100` while listing about 2,000 holders;
  - all 20 request_id conflicts accepted;
  - about 1,030 req/s handled, p99 latency about 1.5 s, 6–8k 503s.
- Issues hit:
  - System Python (C:\Python312) isn't writable, so tests run inside the container.
  - Host port 8001 was already taken, so seller1 now maps to 18001 (`SELLER1_PORT`).
- New known weaknesses are listed above (client lag during the burst, 503 on acquire timeout, the naive hot-row slowness).

### 2026-09-24 — Session 4 (continued): port 8001 and the GitHub push
- Port 8001 was held by another project's container (`sourcerer_backend-api-1`, restart policy unless-stopped), not by this project.
  - The process listening on the port was `com.docker.backend`, i.e. Docker Desktop itself, so killing that PID would have killed Docker Desktop.
  - Stopped that container instead, at the user's request. Undo with `docker start sourcerer_backend-api-1`.
- seller1 is back on host port 8001 (the `SELLER1_PORT` override is kept). Checked with curl: reset, buy and status all work.
- Added `.gitattributes` (LF line endings) and exec bits on the scripts, so a Windows clean checkout doesn't break the bash scripts. A fresh clone passed `scripts/test.sh`.
- Added the remote https://github.com/Hariish-A/Ticket-Stampede and pushed `main`.

### 2026-09-24 — Session 4 (continued): M2, the safe seller passes
- Built:
  - `tickets` table: N rows per sale; PK on ticket_no; UNIQUE on request_id and on user_id; CHECKs; a partial index on unsold rows.
  - `ConstrainedAllocator`: lookup → claim → on UniqueViolation look up again (D13); `resolve_existing` handles replay, 422, and D7 existing.
  - `SkipLockedAllocator`: SKIP LOCKED claim, then a blocking claim, then a re-lookup before 409 (D14).
  - `/status` as a single statement, so the count and the list come from one snapshot.
  - Seller integration tests (test stage in the seller Dockerfile, `seller-tests` compose service); `scripts/c1.sh`.
  - Default ALLOCATOR is now `skiplocked`.
- **Mistakes caught in this session, including the AI's own (useful for DECISIONS.md and the logs):**
  1. **c1.sh attacked the wrong seller.** The first C1 run reported naive PASS. The report's `allocator` field showed both runs were served by skiplocked. Cause: `docker compose run buyer` also starts the buyer's dependencies, re-read the compose file with ALLOCATOR unset, and silently recreated seller1 on the new default. (M1's naive.sh only worked because naive was the default then.) Fix: `--no-deps`, plus a buyer `--expect-allocator` guard that refuses to run against the wrong seller.
  2. **The probe design was wrong.** Replays and conflicts targeted the earliest 300 request_ids, on the assumption they'd be winners. With a 1,000-request burst at t=0, winning is effectively random, and 0 of 20 conflict probes hit a winner, so U2 "failed" against a correct seller. Fix: phase-2 probes built from actual phase-1 outcomes (D15). U2 now only counts conflicts on request_ids bound to a ticket.
  3. **A U2 verifier bug the AI wrote while fixing (2)** (the bound-map included the conflicting user's own confirmations) was caught immediately by the existing planted-defect test.
  4. **A real seller race found by designing U5** ("a ticket holder is never told sold out"). Twins racing for the last ticket: the loser's blocking claim waits on its twin's row and then answers 409. Reproduced first by a test (1/30 twins told "sold out"), then fixed with a re-lookup before 409. The race-sensitive tests passed 5 out of 5 reruns (100 iterations).
- Mutation check: removing the SKIP LOCKED fallback makes 2 integration tests fail, so they test what they claim.
- Results: `results/*c1-naive`, `results/*c1-skiplocked`.

### 2026-09-24 — Session 4 (continued): M3, a buyer we can trust at scale
- Built:
  - `coordinator.py`: splits the schedule across P spawn-processes with a shared t0 (CLOCK_MONOTONIC is system-wide).
  - `runner.py`: open-loop with an in-flight cap (D16); closed-loop with an optional deadline; `worker_main` records CPU use per process.
  - `auditor.py`: live `/status` polling with per-snapshot and between-snapshot checks (A3, counted as core alongside I1–I4).
  - Client health in every report.
  - `buyer calibrate`; nginx `lb` service with a canned-response server on :8081; `scripts/calibrate.sh`, which also samples container CPU.
- **Mistake caught (the AI's own design):** the first calibration offered 60k req/s to one process. The M1 open-loop runner had no in-flight bound, so once behind schedule it stopped sleeping and spawned about 300k tasks and new TCP connections. It ran 7 minutes: 0 responses, send lag p99 424 s. The root cause is in the design, not calibration-specific: an overloaded open-loop client must not grow without bound. Fixed with a per-process semaphore, with `sent` taken after acquiring a slot, so any backlog is reported as send lag (D16). Calibration now measures the ceiling closed-loop (D17).
- Environment:
  - Docker Desktop had stopped mid-session, so I restarted it.
  - postgres had no restart policy and stayed down, so seller1 crash-looped. Added `restart: unless-stopped` to postgres; M7 must check this doesn't auto-restart a killed postgres.
  - A corrupted build cache after the restart was fixed by rebuilding.
- The heredoc-based Python edits turned `"
"` into literal newlines twice. Fixed with the Edit tool; use Edit for such changes.
- Results: `results/*-calibrate`, `results/*-calibrate-container-cpu.txt`, `results/*c1-{naive,skiplocked}` (M3 runs).

### 2026-09-24 — Session 4 (continued): M4, choosing the allocation strategy from evidence (C2)
- Built:
  - `CounterAllocator`: a single data-modifying CTE that increments `sale.sold` and fills that ticket, so both commit or roll back together.
  - `SerializableAllocator`: a SERIALIZABLE read-lowest-then-write transaction, retrying up to 50 times on 40001/deadlock, then 503.
  - Per-allocator counters on `GET /metrics`, which the buyer diffs across each run.
  - `buyer compare` (side-by-side table of saved reports); `scripts/c2.sh`.
  - All 10 race integration tests are parametrised over the 3 safe strategies (31 pass).
- Results (`results/*c2-summary.md`): see D19 in Plan.md. All 6 runs pass every check.
  - Brief workload: modest gap (sold out 0.66 / 0.94 / 1.79 s).
  - Large sale: decisive. skiplocked sold 5,000 in 5.4 s; counter was capped at about 250 claims/s; serializable sold 1,472 with 24,927 retries.
- Honest framing for DECISIONS.md: the Session 3 recommendation of SKIP LOCKED was a guess. The measurement confirms it under contention, but shows it barely matters at 100 tickets. The measurement also found a cost nobody predicted: skiplocked's sold-out path does 4 queries.

### 2026-09-24 — Session 4 (continued): M5, how much load, and where is the bottleneck
- Built:
  - Server-Timing header on /buy (acq, alloc, handler). The buyer parses it and reports time outside the handler.
  - `sweep.sh` (steady open-loop steps; samples docker stats CPU and pg_stat_activity during each step; discarded warm-up) plus `buyer.sweep_report`.
  - `profile.sh` (py-spy in the seller image with SYS_PTRACE; `pg_test_fsync`) plus `buyer.profile_report`.
  - `hotrow.sh` (commit flush on/off experiment); `d10.sh` (compose network vs host port).
- **Fix found by the evidence (D20):** the sold-out fast path, 4 queries → 1. Knee 1,000 → 1,500 req/s; p99 at 1,000/s 310 → 15 ms. New integration test × 3 strategies (34 pass).
- **Hypothesis confirmed by intervention:** the counter's ~250 claims/s is the disk flush (`pg_test_fsync` about 372/s) with a row lock held across it. With flush off, counter sells 5,000 in 3.8 s; skiplocked barely changes (group commit).
- **D10 confirmed:** the host port adds about 1 ms p50.
- **Measurement mistakes caught (all runs moved to `results/discarded/` with reasons):**
  1. The after-fix sweep's first step measured a cold start (p99 185 ms at 250/s). I first "fixed" this by changing the knee rule's baseline. That was the wrong fix: it made the contaminated step flag itself as the knee. The right fix was a discarded warm-up step (D21) and a rerun.
  2. Hot-row "off" runs were really "on": ALTER SYSTEM is outranked by the `-c synchronous_commit=on` postgres command-line flag in our compose. Caught because the script prints SHOW synchronous_commit. Fixed with ALTER DATABASE plus a seller restart and a hard check that aborts if the setting didn't apply.
  3. D10 single runs (direct always first, right after `up`) showed direct p99 280 ms: a cold start mistaken for a path effect. Fixed with a warm-up and 3 alternating rounds.
  4. A Python edit script with a syntax error silently applied none of the fixes, so attempt 2 repeated both flaws. Lesson: edit scripts with the Edit tool, or a Python file written with the Write tool; `bash -n` before running.
- Tried and failed: `py-spy --native` (blocking mode needed; then "Failed to merge native and python frames" on uvloop). Stated as a limit in the bottleneck note.

### 2026-09-24 — Session 4 (continued): M6, the datastore goes slow for 10 s
- Built:
  - toxiproxy service (sellers route through it when `DB_HOST=toxiproxy`); `buyer.faults` adds and removes a latency toxic on the buyer's own clock.
  - Seller: `not_attempted` vs `unknown` 503s (D22); a definite answer is returned even if releasing the connection fails; throttled failure logs; `Admission` fail-fast ASGI middleware (`MAX_INFLIGHT`, off by default, D24).
  - Buyer: retries with the same request_id, plus a retry budget (D23); per-buyer outcomes (recovered by retry, bought on retry, turned away (known), still unknown); per-second timeline; `compare --timeline`.
  - `scripts/slowdb.sh` with 5 variants.
- Results: `results/M6-slowdb.md`. All variants pass every invariant.
  - Baseline: metastable outage, 1,693 orphans, 6,856 unanswered.
  - Retry budget: 0 / 0, sold out 27.9 s vs 51.8 s.
  - Fail-fast: seller responsive, orphans 29, but 20,958 turned away by the storm.
  - Closed-loop (C4): p99 65 ms vs 9.9 s for the same stall.
- **Mistakes caught (runs discarded with reasons):**
  1. The client held in-flight slots through retry backoff, throttling its own new sends (the client flattering the seller).
  2. The outcome classification lumped known-not-bought (`not_attempted` only) with unknown.
  3. U2 counted shed 503s as acceptances. While fixing it, a new test found that a leaked ticket on a retry would rebind the request_id and hide the leak; fixed.
- The AI doubted that server-side shedding would help, because M5 showed the web stack dominates per-request cost. The measurement disagreed: shedding in ASGI, before FastAPI, is cheap (4.5k req/s answered). Recorded as such.
