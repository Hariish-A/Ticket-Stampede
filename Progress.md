# Progress

> A running log that lets any AI agent continue where the last one stopped.
> Append new entries at the bottom of the log. Keep "Current state" and "Next up" current.

## Current state
- **Phase:** M1 is done (the naive seller gets caught). M2 is next, when the user says "start M2".
- **Runs?** Yes: `./scripts/test.sh` (17 unit tests pass) and `./scripts/naive.sh` (the naive seller FAILs I1–I4 in 3 out of 3 runs at 50k requests).
- **Tests:** 17 pytest unit tests (verifier + schedule), run inside the buyer image.
- **Repo:** git initialised locally, M1 committed. The GitHub push is blocked: `gh` isn't installed, and a private repo has to be created (waiting on the user).

## Next up
1. The user creates the private GitHub repo (or authenticates `gh`), then push.
2. M2: the `skiplocked` allocator, idempotency lookup, D7, 422, the confirm-before-409 check, a single-snapshot /status, seller integration tests, `scripts/c1.sh`.

## Known weaknesses / open issues
_(These feed into the "where it breaks" section of DECISIONS.md.)_
- The instances cache "sold out" in memory, and a /reset sent to one instance doesn't clear the others' caches unless we add invalidation (e.g. Postgres LISTEN/NOTIFY). This flaw is in the AI's own Session 2 caching suggestion.
- user_id isn't authenticated, so the one-ticket-per-user rule can be bypassed by making up new user_ids. /reset isn't authenticated either.
- The load client and the seller share one machine's CPU, so throughput numbers depend on the machine.
- A single Postgres node is a single point of failure; asynchronous replication would make failover lose confirmed sales.
- (M1) **Single-process buyer lags during the opening burst**: its send lag reaches p99 71–98 ms and max 240–310 ms when 1,000 requests are scheduled at t=0. The client-health metric shows this. M3 (multiprocess plus calibration) needs to fix and quantify it.
- (M1) **A pool-acquire timeout answers 503 "unknown", but the outcome is actually known**: the request never reached the database, so nothing happened. M6 should separate "not attempted, safe to retry" from "unknown outcome".
- (M1, to investigate in M4/M5) **The naive seller handles only about 200–400 buys/s**. There were 6–8k 503s per run, and p90 latency was about 1 s, which matches the 1 s acquire timeout. Hypothesis: every buy does `UPDATE sale` on the single row, and each of those commits waits for a WAL fsync while holding the row lock. So buys queue behind fsync latency (the "hot row" problem). The C2 `counter` strategy would have the same problem. Unverified until measured.

## Open questions for the user
- GitHub: create an empty **private** repo and send the URL, or run `gh auth login` once `gh` is installed. I'll push M1 straight after.

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
