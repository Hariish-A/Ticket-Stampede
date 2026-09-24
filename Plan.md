# Plan

> The game plan: what we're building, how, and why. Update it when decisions are made or changed.
> Rules for editing it are in `Instructions.md`.

## 1. Problem statement (verbatim summary: Problem 1, "Ticket Stampede")
Evaluated on backend engineering and architecture. 50,000 people want 100 tickets, and they all arrive within the same 60 seconds.

**Part A: the seller.** Three endpoints:
- `POST /reset {count}`: wipes all state and starts a fresh sale.
- `POST /buy {user_id, request_id}`: returns a ticket number, or a clear sold-out response.
- `GET /status`: the number sold, plus the full list of which user holds which ticket number.

Invariants that must hold under any load:
1. Never sell more tickets than exist.
2. Never issue the same ticket number twice.
3. If the same request_id arrives twice, the buyer gets one ticket, not two.
4. The count in /status always matches the tickets actually issued.

Language, framework and datastore are our choice, justified in the write-up.

**Part B: the buyer (load client).** Configurable number of concurrent buys. Replays duplicate request_ids. Verifies the invariants afterwards through /status. Reports requests/sec, p50, p99, and a PASS/FAIL for each invariant.

**What they want to see:**
- A naive version first, with the client catching it overselling, then the fix. Both runs go in the write-up.
- How much load before latency degrades. Where the bottleneck is, and how we know (not guess).
- What happens when the datastore goes slow for 10 seconds mid-sale.
- Correctness first; speed only counts once nothing is oversold.

**Take it further (optional; do one properly):**
- (TF1) 3 seller instances behind a load balancer, no app-level lock between them, all 4 invariants hold.
- (TF2) Kill the datastore mid-sale and bring it back: no oversell, no duplicate ticket numbers, no lost confirmed sale. Show the run.
- (TF3) Waitlist: when tickets run out, buyers queue. A reservation not confirmed within 30 seconds returns to the pool and goes to the next person in the queue. This turns the counter into a state machine.
- (TF4) Distributed load client across processes. Prove the throughput numbers are not limited by our own client.

## 2. Goal and scope
**Core (must ship)**
- Seller: `/reset`, `/buy`, `/status`, with all 4 invariants held under concurrency, and 1 ticket per user (D3).
- Buyer:
  - configurable load, run as multiple processes;
  - duplicate replays;
  - requests/sec, p50, p99;
  - PASS/FAIL per invariant.
- A naive version that fails, and a fixed version that passes (C1), with both runs saved and quoted in DECISIONS.md.
- Load before latency degrades, the bottleneck identified with evidence, and the 10-second datastore slowdown.

**Take-further items**
- **TF2 (the deep one):** kill Postgres mid-sale and restart it. No oversell, no duplicate ticket numbers, no lost confirmed sale.
- **TF1:** 3 seller instances behind nginx, with no lock in the app.
- **TF4:** the buyer's own limit measured, which comes from A4.

**Beyond the brief (chosen in Session 3)**
- **A1:** the buyer sends on a fixed schedule and measures latency from the scheduled send time, which corrects for coordinated omission.
- **A2:** the buyer keeps a ledger of what it was told and compares it with `/status`. It detects phantom tickets (confirmed to a buyer, but missing from `/status`) and orphaned tickets (sold, but the buyer was never told).
- **A3:** a live invariant auditor that polls `/status` throughout the sale.
- **A4:** the buyer's ceiling measured against a target that answers instantly (nginx), plus a check on every run that shows whether the client fell behind its own schedule.
- **C1:** naive, then fixed.
- **C2:** three allocation strategies measured against each other: `SERIALIZABLE` with retries, a single counter row, and `SKIP LOCKED` on pre-created ticket rows.
- **C4:** closed-loop vs open-loop client, run against the same datastore stall.

**Also in scope** (the user's Critical, High and Medium questions)
- Idempotency.
- Postgres design.
- Fault tolerance: timeouts, fail fast, 503 for unknown outcomes.
- FastAPI.
- Load balancing.
- Caching: the sold-out cache, conditional (M9). Build it only if measurements show the sold-out path is DB-bound.
- The requirement gaps.

**Out of scope (named in DECISIONS.md)**
- TF3 (waitlist).
- Rate limiting per user or IP, and authentication.
- A multi-node Postgres or any replication.
- Load balancer redundancy.
- C3 as a formal experiment. We still implement timeouts and fail-fast, but don't compare them against an unbounded version.

## 3. Architecture

```
            buyer (P processes, in a container on the compose network)
            ├── coordinator: builds the schedule, resets, starts workers, verifies, reports
            ├── workers x P: aiohttp, open- or closed-loop, record a ledger + timings
            └── auditor: polls /status during the run (A3)
                    │ HTTP
                  nginx :8080  (least_conn, keepalive upstream; /calibrate returns a static 200 for A4)
          ┌─────────┼─────────┐
       seller1   seller2   seller3     FastAPI + uvicorn (1 worker each), asyncpg pool (max 20 each)
          └─────────┼─────────┘
               toxiproxy         (injects latency or cuts the connection for the slowdown test)
                    │
               postgres 16       (fsync=on, synchronous_commit=on, named volume)
```

- The buyer runs **inside** the compose network by default. Docker Desktop's port-forwarding from the Windows host can itself become a bottleneck, and we will measure that rather than assume it.
- Single-instance runs go straight to `seller1`, skipping nginx. TF1 runs go through nginx.
- Sellers keep no state that correctness depends on. Every invariant is enforced by Postgres.

### Components
| Component | Responsibility | Tech |
|-----------|----------------|------|
| `seller/` | HTTP API, allocation strategies, idempotency, timeouts, Server-Timing header | Python 3.12, FastAPI, uvicorn, asyncpg |
| `seller/schema.sql` | Tables and constraints: the invariants enforced by the database | Postgres 16 |
| `buyer/` | Schedule generator, multiprocess workers, ledger, verifier, auditor, reporter | Python 3.12, aiohttp, multiprocessing |
| `infra/` | docker-compose, nginx.conf, toxiproxy config | Docker Compose |
| `scripts/` | One script per named scenario (naive vs safe, C2, C4, sweep, slow-db, kill-db, tf1, calibrate) | bash + the buyer CLI |
| `results/` | Saved JSON and Markdown reports for every run quoted in DECISIONS.md | — |
| `tests/` | pytest: verifier unit tests ("testing the tester"), seller integration tests | pytest |

### Data model (`schema.sql`)
```sql
sale(id=1 CHECK, epoch bigint, total int, sold int)            -- a single row; `sold` is used only by the counter strategy
tickets(ticket_no int PRIMARY KEY, user_id text UNIQUE, request_id text UNIQUE, sold_at timestamptz,
        CHECK ((user_id IS NULL) = (request_id IS NULL)))       -- N rows created at /reset; a NULL user_id means unsold
naive_sales(ticket_no int, user_id text, request_id text)       -- NO constraints: used only by the naive strategy
```
- **What the database guarantees on its own:**
  - Invariant 2: the primary key on `ticket_no`.
  - Invariant 1: exactly N rows exist.
  - Invariant 3: `UNIQUE(request_id)`.
  - D3: `UNIQUE(user_id)`.
- **`/reset`** runs in one transaction: `TRUNCATE`, create rows 1..N, `epoch = epoch + 1`, `NOTIFY sale_reset`.
  - `TRUNCATE` takes an ACCESS EXCLUSIVE lock, so buys already running finish before the reset. A buy that starts after the reset belongs to the new sale.
  - Every response carries the epoch, so the buyer can tell if a reset happened during its run.

### The `/buy` flow (all safe strategies)
1. **Look for an existing sale.** One query: `SELECT … WHERE request_id=$r OR user_id=$u`.
   - Same request_id, same user → **200, `replayed:true`**.
   - Same request_id, different user → **422 `request_id_conflict`**.
   - Same user, different request_id → **200, `existing:true`** (D7).
2. **Claim a ticket**, using the strategy set by the `ALLOCATOR` environment variable:
   - `skiplocked`: `UPDATE tickets SET … WHERE ticket_no = (SELECT ticket_no … WHERE user_id IS NULL ORDER BY ticket_no LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING ticket_no`.
   - `counter`: `UPDATE sale SET sold=sold+1 WHERE sold<total RETURNING sold`, then fill that row. Every buyer waits on the one `sale` row.
   - `serializable`: a `SERIALIZABLE` transaction (read the lowest unsold ticket, then update it), retried on error 40001, with the retry count recorded.
   - `naive`: `SELECT count(*) FROM naive_sales`, **await**, then `INSERT count+1`. No idempotency check. Built to fail.
3. **Two copies of the same request at the same moment.** Both pass step 1, then one of them hits a `UniqueViolation` at claim or commit time. We roll back that transaction and run step 1 again, which returns the winner's ticket. The rolled-back claim frees its row.
4. **Sold out.** With `SKIP LOCKED`, "no row returned" might only mean the remaining rows are locked by transactions that could still roll back. Before answering 409, we confirm with a check that doesn't skip locked rows: `NOT EXISTS (… user_id IS NULL)`. Otherwise a buyer could be told "sold out" while a ticket stays unsold.
5. **Responses:**
   - 200 `{status:"purchased", ticket_no, epoch, replayed, existing}`
   - 409 `{status:"sold_out", epoch}`
   - 422 `{status:"request_id_conflict"}`
   - **503 `{status:"unknown", retry_with_same_request_id:true}` with Retry-After.**
6. **Timeouts:**
   - Waiting for a pool connection: about 1 s.
   - `command_timeout` on each query: about 2 s.
   - Any timeout or dropped connection after the transaction has started → **503, never 409.** We don't know whether the transaction committed.
   - Ordering: buyer timeout > nginx timeout > app timeout > query timeout.
7. **Server-Timing header**: time spent waiting for a connection, time in the database, and total time. The buyer adds these up across all requests, which shows where the time goes (the bottleneck) from measurements rather than guesswork.

### `/status`
- One `REPEATABLE READ` read-only transaction returns `{epoch, total, sold, holders:[{ticket_no,user_id}]}`.
- **Safe strategies:** `sold` comes from the same snapshot as the list. Invariant 4 holds by construction.
- **Naive strategy:** reports its own `count(*)` next to the list, so any disagreement shows.

### Sold-out cache (M9, conditional)
- Built only if profiling shows the sold-out path is limited by the database.
- **What it holds:** each instance caches `{epoch, sold_out:true, winners by request_id and by user_id}`. It is filled only after the database confirms the sale is sold out.
- **How it's cleared:**
  - `LISTEN sale_reset` clears it when any instance resets the sale.
  - If the listener connection drops, the cache is cleared too, because resets can't be heard while disconnected.
- It is measured with the cache on and off.

### The buyer
- **Schedule:** the coordinator builds a list of `(t_offset, user_id, request_id, kind)` and deals it out to P worker processes. Workers share a start time `t0` (the same host clock).
- **Kinds of request:**
  - fresh;
  - `dup_concurrent`: the same request_id twice, at the same instant;
  - `dup_sequential`: repeated later;
  - `dup_after_sellout`;
  - `same_user_new_rid`: exercises D7;
  - `rid_conflict`: the same request_id with a different user, expecting 422.
- **Two loop modes:**
  - `--rate R` is **open-loop** (A1). Latency is measured from the scheduled send time, and the gap between scheduled and actual send time is also recorded.
  - `--concurrency C` is **closed-loop**, kept only for the C4 comparison.
- **Retries:** `--retry-unknown K` retries a 503 or timeout with the same request_id (A2, TF2).
- **Ledger:** one line per attempt: request_id, user, scheduled/sent/done times, HTTP status, ticket, epoch, flags, Server-Timing.
- **Verifier.** For each invariant, PASS or FAIL with a count of offending examples, checked against both `/status` and the ledger:
  - **I1:** `sold ≤ total`, `len(holders) ≤ total`, and the number of distinct tickets confirmed to the client ≤ total.
  - **I2:** no ticket number appears twice in `/status`, and no two different request_ids were confirmed the same ticket.
  - **I3:** each request_id got at most one distinct ticket; each user holds at most one ticket; every replay got the same ticket.
  - **I4:** `sold == len(holders)`. There are no phantoms: every confirmed (request, user, ticket) appears in `/status`. The auditor saw no violations during the run.
  - **Orphans** (sold in `/status` but never confirmed to the client) are reported as a number, not a failure.
- **Report:**
  - requests/sec (overall, and for the period after sellout);
  - p50, p90, p99 and max latency, measured both from the scheduled time and from the actual send;
  - responses broken down by status code;
  - Server-Timing breakdown;
  - **client health**: how far sends fell behind schedule (p99 and max), plus worker CPU;
  - saved to `results/<timestamp>-<scenario>.{json,md}`.

### Alternatives considered and rejected
| Option | Why rejected | Evidence |
|--------|--------------|----------|
| Django | Its ORM hides the allocation SQL. Its async ORM still runs blocking database calls in a thread pool, and it adds fixed work to every request. | Reasoning (Session 3) |
| Redis + Lua | Durability needs `appendfsync always`, and the Redis itself can't enforce the invariants with constraints | Reasoning (Session 2) |
| Redis in front of Postgres | Writing to two stores means they can disagree, which puts invariant 4 at risk | Reasoning |
| Microservices | Splitting the seller adds network calls where partial failures break the invariants | Reasoning |
| `serializable` (SERIALIZABLE + retry) | Correct, but under contention nearly every buyer reads the same lowest ticket and aborts. Large sale: 24,927 retries, 241 gave up, only 1,472/5,000 sold by the end of the run, and 93% of requests got 503. | `results/*c2-summary.md` (M4) |
| `counter` (single hot row) | Correct, but every claim queues on one row lock: about 250 claims/s. Large sale: 4,704/5,000 sold, 16,260 503s, p50 1 s. Acceptable at 100 tickets (sold out in 0.94 s vs 0.66 s). | `results/*c2-summary.md` (M4) |
| Closed-loop client | Hides stalls (coordinated omission): the same 10 s stall reads p99 65 ms closed-loop vs 9.9 s open-loop, because it sent 0–3 req/s during the stall | `results/M6-slowdb.md` |

## 4. Design decisions
| # | Decision | Reason | Decided by | Date |
|---|----------|--------|------------|------|
| D1 | One repo, two programs (seller, buyer); no microservices | The seller has one job; splitting it adds network calls where partial failures can break the invariants | User (on AI recommendation) | 2026-09-24 |
| D2 | Postgres as the single source of truth | Unique/check constraints enforce invariants 2 and 3 inside the database; confirmed sales survive a kill (WAL + fsync), which TF2 needs | User | 2026-09-24 |
| D3 | Limit one ticket per user_id, enforced by a database constraint | A product rule the brief doesn't state; it also gives a buyer who hit a timeout a second way to recover their ticket | User | 2026-09-24 |
| D4 | Go deep on TF2 (kill the datastore); also do TF1 (3 instances) | TF1 comes almost free with a stateless seller and database constraints; TF3 (waitlist) breaks the sold-out cache and costs too much | User (on AI recommendation) | 2026-09-24 |
| D5 | Buyer in Python, running as multiple processes | Matches the seller's language; multiprocess is needed for TF4 | User | 2026-09-24 |
| D6 | FastAPI + asyncpg with the SQL written out in full (not Django, no ORM) | The allocation SQL must be visible and defensible; fully async database calls; little per-request overhead | User | 2026-09-24 |
| D7 | A user who already holds a ticket and sends a new request_id gets **200 with their existing ticket** (`existing:true`) | Friendlier, and it recovers orphaned tickets after a timeout | User | 2026-09-24 |
| D8 | Scope: build the Critical/High/Medium questions; drop rate limiting, multi-node HA and the monorepo debate; differentiators A1–A4 and C1, C2, C4 | Depth over breadth | User | 2026-09-24 |
| D9 | Milestones are vertical slices: each ends in something that runs, with a demo command and acceptance criteria | Always have something working to show if time runs out | User | 2026-09-24 |
| D10 | The buyer runs inside the compose network by default | Docker Desktop's host port-forwarding may be a bottleneck; to be verified in M5 | AI (proposed; user did not object) | 2026-09-24 |
| D11 | One uvicorn worker per container; scale by adding instances | Makes 1-instance vs 3-instance runs simpler to reason about; the naive version still races because it awaits the database between read and write | AI (proposed) | 2026-09-24 |
| D12 | The opening of the sale is modelled as a **burst** (default: 1,000 requests at t=0), then a fixed rate | "50k in 60 s" averages about 830/s, but real on-sales spike at the opening, and the race window is only the first ~100 sales. A purely uniform arrival would barely exercise it. | AI (M1) | 2026-09-24 |
| D13 | The safe `/buy` uses **no explicit transaction**: a lookup, then a claim that is one atomic `UPDATE`, then (on a UniqueViolation) the lookup again | The constraints stop double sales, not a lock held across statements. Dropping BEGIN/COMMIT saves 2 round trips, and row locks are held for exactly one statement. | AI (M2) | 2026-09-24 |
| D14 | SKIP LOCKED claim → blocking claim → **look up again** before answering 409 | Without the fallback, a buyer is told "sold out" while the last ticket is mid-claim and about to roll back. Without the re-lookup, a twin that loses the last ticket to its own duplicate is told "sold out". Both were reproduced by tests. The cost is extra queries on the sold-out path (to be measured in M4/M5). | AI (M2) | 2026-09-24 |
| D15 | Buyer probes (post-sale replays, new request_ids, conflicts) are a **second phase built from the ledger** of phase 1 | The first version guessed that the earliest requests would win. With a burst at t=0 that's false, so the probes silently tested losers only. | AI (M2) | 2026-09-24 |
| D16 | The open-loop client caps in-flight requests per process (`--max-inflight`, default 2000). The send timestamp is taken **after** a slot is acquired. | Without a cap, an overloaded client floods itself: in the first calibration, one process offered 60k/s spent 7 min and got 0 responses. With the cap, any backlog shows up as client send lag instead of disappearing. | AI (M3) | 2026-09-24 |
| D17 | The client ceiling is measured **closed-loop** against a zero-work nginx target, then checked open-loop at half the ceiling | The target never stalls, so closed-loop hides nothing, and it measures the maximum directly. The open-loop check shows the client keeps its schedule at real test rates. | AI (M3) | 2026-09-24 |
| D18 | The live auditor runs inside the coordinator process while the workers fire, polling `/status` every 100 ms | The coordinator is otherwise idle, so no extra process is needed. The observer effect (about 10 extra /status requests/s on the seller) is small and stated. | AI (M3) | 2026-09-24 |
| D19 | **`skiplocked` stays the default, now chosen on evidence (C2).** | 100 tickets: sold out in 0.66 s vs 0.94 (counter) vs 1.79 (serializable); fewest 503s. 5,000 tickets: sold all 5,000 in 5.4 s with p50 55 ms, while counter reached about 250 claims/s and serializable 1,472 tickets with 24,927 retries. Caveat: at the brief's 100 tickets the gap is modest. | AI proposal, confirmed by measurement (M4) | 2026-09-24 |
| D20 | **Sold-out fast path**: the lookup query also tests `NOT EXISTS (unsold ticket)` in the same snapshot; if the buyer holds nothing and nothing is unsold, answer 409 from that one query | 99.8% of traffic is sold-out. 4 queries became 1: knee 1,000 → 1,500 req/s, p99 at 1,000/s 310 → 15 ms. Correct because committed sales are permanent, and a twin committing later held an unsold row in this snapshot. Covered by a new integration test × 3 strategies. | AI (M5), measured | 2026-09-24 |
| D21 | Performance experiments discard a warm-up step and alternate the order of compared variants | A cold seller (pool growing 5 → 20, cold caches) has p99 of about 180–290 ms for its first seconds. It contaminated one sweep and one D10 comparison before this rule. | AI (M5) | 2026-09-24 |
| D22 | Two kinds of 503: `not_attempted` (no connection obtained, nothing sent: known not bought) vs `unknown` (a statement was sent, no answer: maybe bought) | A buyer (and the verifier) can tell "definitely not" from "maybe". This was the M1 known weakness. | AI (M6) | 2026-09-24 |
| D23 | The buyer retries unclear answers with the same request_id (`--retry-unknown`, exponential backoff + jitter), optionally under a **retry budget** (`--retry-rate`, token bucket; over-budget retries wait, never dropped). The in-flight slot covers the first attempt only. | Measured: without a budget, a 10 s stall became a metastable ~40 s+ outage (1,693 orphans, 6,856 buyers never answered). With a 200/s budget: 0 orphans, 0 unanswered, sold out 27.9 s vs 51.8 s. | AI (M6), measured | 2026-09-24 |
| D24 | Seller fail-fast admission (`MAX_INFLIGHT`, a pure ASGI middleware that sheds /buy with an immediate 503) — **implemented, default OFF, pending the user's decision** | Measured: keeps the seller responsive through a retry storm (p99 back to ~300 ms after the stall; orphans 1,693 → 29). But at 64 it would also shed part of the brief's 1,000-request opening burst. | Pending (user) | 2026-09-24 |
| D25 | "Mid-sale" slowdown uses a 15,000-ticket sale | With 100 tickets the sale ends in ~0.1 s, so a stall at t=5 s would only hit sold-out answers | AI (M6) | 2026-09-24 |
| D26 | `/buy` never answers 500: any exception becomes result / `unknown` / `not_attempted` depending on how far the request got; the buyer retries any 5xx | The first kill trial produced 500s from an exception type missing from the error list (asyncpg `InternalClientError` on connection release). The buyer treated 500 as final, leaving 2 orphans. | AI (M7) | 2026-09-24 |
| D27 | TF2 is proved with a **control run** (`synchronous_commit=off`) that must fail | It lost 6 confirmed sales and resold them. `/status` looked perfect; only the buyer's ledger caught it. Without the control, "0 phantoms" would be unfalsified. | AI (M7) | 2026-09-24 |
| D10 ✔ | Confirmed by M5 measurement: the host port path adds about 1 ms p50, 1.5–4 ms p99 at 800 req/s | 3 alternating rounds | Measured (M5) | 2026-09-24 |

## 5. Testing and verification strategy
| Layer | What | What it proves |
|-------|------|----------------|
| Verifier unit tests | Feed the verifier synthetic ledgers and `/status` payloads containing each kind of violation (oversell, duplicate ticket, double issue on a replay, count mismatch, phantom), and assert it FAILs each one. A clean payload must PASS. | **The tester can actually catch failures.** Otherwise a PASS means nothing. |
| Seller integration tests (pytest against the real Postgres in compose) | Two copies of one request_id at the same instant; the same user with two request_ids; a request_id conflict returning 422; selling out exactly N with N+k concurrent buyers; reset; a winner's replay after sellout | Each idempotency race and edge case, run against real concurrency |
| Scenario scripts (`scripts/`) | One script per milestone demo; each saves a report to `results/` | The numbers quoted in DECISIONS.md can be reproduced |

## 6. Milestones: each one ends in something that runs
Rules:
- A milestone counts as **done** only when its demo command works from a clean `docker compose up` and its acceptance criteria are met.
- Each milestone's report is saved in `results/`, and `Progress.md` is updated.
- If time runs out, everything up to the last finished milestone is still a coherent submission.

---

### M1: The naive seller gets caught (end-to-end skeleton) · ~3.0 h · ✅ DONE 2026-09-24
**Build**
- Repo layout and a `docker-compose.yml` with postgres and seller1.
- `schema.sql`.
- The FastAPI seller with `/reset`, `/buy`, `/status`, using the `naive` strategy.
- The buyer as a single process, open-loop:
  - duplicate modes;
  - ledger;
  - a verifier for I1–I4 plus phantoms and orphans (A2);
  - a report with requests/sec, p50 and p99.
- Verifier unit tests.

**Deliverable**
- `docker compose up -d`, then `./scripts/naive.sh`.
- The report shows **I1 oversold FAIL** (plus I2, I3 and I4 as they occur), and it's saved.

**Acceptance**
- The naive run fails reproducibly (3 runs out of 3).
- The verifier unit tests pass, including a FAIL case for each kind of violation.

### M2: The safe seller passes (core brief complete) · ~2.0 h · ✅ DONE 2026-09-24
**Build**
- The `skiplocked` strategy.
- The existing-sale lookup: replay, D7, and 422.
- UniqueViolation handling (catch, roll back, look up the existing sale again).
- The confirm-before-409 sold-out check.
- `/status` read as one snapshot.
- Seller integration tests.

**Deliverable**
- `./scripts/c1.sh` runs the same load against `naive` (FAIL), then `skiplocked` (all PASS).
- Both reports are saved.

**Acceptance**
- All 4 invariants PASS on 50,000 requests for 100 tickets with duplicate replays.
- Integration tests are green.
- **This is the minimum complete submission.**

### M3: A buyer we can trust at scale (A3, A4, TF4) · ~2.0 h · ✅ DONE 2026-09-24
**Build**
- The multiprocess coordinator and workers.
- The live auditor (A3).
- The client-health section: how far sends fell behind schedule, and worker CPU.
- The closed-loop mode.
- nginx with a `/calibrate` static route.

**Deliverable**
- `./scripts/calibrate.sh` runs the buyer against `/calibrate` with 1, 2, 4 and 8 processes, and produces a table of the client's ceiling.
- `./scripts/c1.sh` now runs multiprocess, with the auditor included.

**Acceptance**
- The client's ceiling is measured.
- The auditor shows 0 live violations on `skiplocked`, and catches violations on `naive`.

### M4: Choosing the allocation strategy from evidence (C2) · ~1.5 h · ✅ DONE 2026-09-24
**Build**
- The `counter` and `serializable` (with retries) strategies, with the retry count exposed.

**Deliverable**
- `./scripts/c2.sh` runs the same load against all 3 strategies.
- It produces a comparison table: requests/sec, p50, p99, retries, invariants.

**Acceptance**
- All 3 strategies pass the invariants.
- The default strategy is chosen from the numbers and recorded in §4. If the data contradicts the SKIP LOCKED guess, we go with the data.

### M5: How much load, and where is the bottleneck? · ~2.0 h · ✅ DONE 2026-09-24 (results/M5-bottleneck.md)
**Build**
- The Server-Timing header, and the buyer's breakdown of it.
- A rate sweep.
- A py-spy capture, and sampling of `pg_stat_activity` wait events.
- A check on D10: the buyer inside the compose network vs on the host.

**Deliverable**
- `./scripts/sweep.sh` steps up the rate and produces a table of p50/p99 against rate, marking the knee.
- A short bottleneck note with the evidence (Server-Timing split, py-spy flamegraph, database waits).

**Acceptance**
- The knee is identified.
- The bottleneck is named, with at least two independent pieces of evidence.
- The client-health data shows the client was not the limit.

### M6: The datastore goes slow for 10 s (fault tolerance + C4) · ~2.0 h · ✅ DONE 2026-09-24 (results/M6-slowdb.md)
**Build**
- toxiproxy placed between the sellers and Postgres.
- Timeouts (pool acquire and `command_timeout`).
- 503 for unknown outcomes, with Retry-After.
- Buyer retries of 503s with the same request_id.

**Deliverable**
- `./scripts/slowdb.sh` injects 10 s of latency mid-sale.
- It runs the open-loop and closed-loop clients against the same stall.
- It produces a latency timeline for each.

**Acceptance**
- The invariants still PASS.
- The stall is visible in the open-loop p99 and hidden in the closed-loop one (C4 evidence).
- Orphaned tickets are counted, and recovered by retrying.

### M7: Kill the datastore mid-sale (TF2, the deep one) · ~1.5 h · ✅ DONE 2026-09-24 (results/M7-killdb.md)
**Build**
- A kill/restart script (`docker kill -s KILL postgres`, then `docker start`).
- The seller's pool recovers.
- The buyer reports phantoms and orphans, with retries.

**Deliverable**
- `./scripts/killdb.sh` kills Postgres mid-sale, then restarts it.
- The report shows all invariants PASS, **0 phantom tickets (no confirmed sale lost)**, and orphans recovered through retries.

**Acceptance**
- 3 out of 3 runs pass.
- Every confirmed ticket survives, including runs where the kill lands during a commit.
- DECISIONS.md explains the durability argument: confirmation is only sent after a durable WAL commit.

### M8: Three instances behind nginx (TF1) · ~0.5 h
**Build**
- seller2 and seller3.
- An nginx upstream using `least_conn` and keepalive.

**Deliverable**
- `./scripts/tf1.sh` reruns C1-safe, slowdb and killdb through nginx with 3 instances.

**Acceptance**
- All invariants PASS with no lock in the app.
- Requests/sec compared between 1 and 3 instances. If throughput doesn't scale, we explain why, using the M5 bottleneck evidence.

### M9 (conditional): The sold-out cache · ~1.0 h
**Only if** M5 shows the sold-out path is limited by the database.

**Build**
- The per-instance cache, keyed by epoch.
- `LISTEN/NOTIFY` to clear it on reset, and clearing it when the listener drops.

**Deliverable**
- A sweep with the cache on and off.
- A reset-across-instances test.

**Acceptance**
- A measured gain.
- No stale sold-out answers after a reset sent to another instance.

### M10: Submission · ~1.5 h
**Deliverable**
- DECISIONS.md (≤2 pages, quoting the saved results).
- A README that works on a clean machine in under 5 minutes.
- The final logs copied.
- A private GitHub repo.

**Acceptance**
- A fresh clone on a clean machine gets through the README and runs `c1.sh` in under 5 minutes.

| Milestone | Hours | Running total |
|-----------|-------|---------------|
| M1 | 3.0 | 3.0 |
| M2 | 2.0 | 5.0 (core complete) |
| M3 | 2.0 | 7.0 |
| M4 | 1.5 | 8.5 |
| M5 | 2.0 | 10.5 |
| M6 | 2.0 | 12.5 |
| M7 | 1.5 | 14.0 |
| M8 | 0.5 | 14.5 |
| M9 | 1.0 | (optional) |
| M10 | 1.5 | 16.0 |

The plan runs about 1 hour over the 15-hour budget. If we need to cut, M9 goes first, then parts of M5's py-spy work.

**Prerequisite:** Docker Desktop must be running on the dev machine. It was installed but not running when checked on 2026-09-24.


## 7. Decision changes (history)
- 2026-09-24 (M6): the buyer's in-flight slot was held through a retry chain, then changed to cover the first attempt only (D23). Holding it let sleeping retries throttle new sends.
- 2026-09-24 (M5): the sold-out answer moved from 4 queries (lookup, SKIP LOCKED claim, blocking claim, re-lookup) to 1 query (D20), after profiling. The full path remains for buyers who might still get a ticket.
- 2026-09-24 (M3): the open-loop client's "no connection limit" (M1) was replaced by a per-process in-flight cap that counts waiting as send lag (D16). The unlimited version collapsed under overload during calibration.
- 2026-09-24 (M2): the post-sale probes were changed from "pre-scheduled against the earliest requests" to "built from actual phase-1 outcomes" (D15). A C1 run showed that 0 of 20 probes had hit a winner.
- 2026-09-24: the milestones were changed from a list of technical tasks to vertical slices, each ending in something that runs (D9, at the user's request).
