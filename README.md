# Ticket Stampede

A ticket seller that must sell exactly N tickets to a stampede of buyers without ever overselling, plus the load client that attacks it and checks the result.

- **Seller** (`seller/`): FastAPI + asyncpg on Postgres 16. Endpoints: `POST /reset`, `POST /buy`, `GET /status`. The allocator is chosen with `ALLOCATOR=skiplocked|counter|serializable|naive`, and the default is `skiplocked` (chosen by the C2 measurement). `GET /metrics` exposes the allocator's counters (retries, fallbacks). Every `/buy` response carries a `Server-Timing` header (pool wait, allocator queries, handler total). The invariants are enforced by Postgres constraints ([schema.sql](seller/schema.sql)); the claim is a single `UPDATE … FOR UPDATE SKIP LOCKED` ([skiplocked.py](seller/app/allocators/skiplocked.py)).
- **Buyer** (`buyer/`): an open-loop load client. It fires a scheduled stampede with duplicate and replayed request ids, then verifies the four invariants against `/status` **and** against its own record of what each buyer was told.

Design and trade-offs: [DECISIONS.md](DECISIONS.md) (written at M10). The working plan is in [Plan.md](Plan.md), and progress in [Progress.md](Progress.md).

## Requirements
- Docker with Compose v2 (Docker Desktop on Windows or macOS). Nothing else; Python runs inside the containers.
- A bash shell for `scripts/` (Git Bash on Windows works).

## Run it (about 2 minutes)
```bash
git clone <this repo> && cd ticket-stampede

./scripts/test.sh      # 39 buyer unit tests + 34 seller integration tests (each race x 3 safe strategies) against real Postgres
./scripts/c1.sh        # the same 51,000-request stampede against the naive seller (FAILs) and the safe one (PASSes)
./scripts/naive.sh     # just the naive seller
./scripts/calibrate.sh # the client's own ceiling against nginx returning canned responses (no seller in the loop)
./scripts/c2.sh        # serializable vs counter vs skiplocked on the brief's sale and on a 5,000-ticket sale (~7 min)
./scripts/sweep.sh     # rate sweep 250..4000 req/s with CPU + Postgres wait sampling -> where is the knee, and why (~5 min)
./scripts/profile.sh   # py-spy on the seller under load + pg_test_fsync
./scripts/hotrow.sh    # is the counter strategy's ceiling the disk flush? (commit flush on vs off)
./scripts/d10.sh       # buyer on the compose network vs through the host's published port
./scripts/slowdb.sh    # Postgres +3 s per answer for 10 s mid-sale: baseline / seller fail-fast / client retry budget / both / closed-loop (~12 min)
./scripts/killdb.sh    # SIGKILL Postgres mid-sale and restart it: 3 runs + a synchronous_commit=off control that must FAIL (~12 min)
./scripts/tf1.sh       # TF1: all of the above against 3 sellers behind nginx (~25 min); or TOPOLOGY=tf1 ./scripts/<any>.sh
```
Each run prints a report and saves it to `results/<timestamp>-<scenario>/`:
- `report.md` and `report.json`, which are committed;
- `ledger.jsonl`, with every request, which isn't committed.

Buyer options (`docker compose run --rm buyer run --help`):

| flag | default | meaning |
|---|---|---|
| `--tickets` | 100 | tickets in the sale |
| `--requests` | 50000 | distinct buyers, one request each |
| `--burst` | 1000 | requests all scheduled at t=0 (the on-sale moment) |
| `--rate` | 1000 | requests/s after the burst (open-loop: sent on schedule, regardless of responses) |
| `--dup-concurrent` / `--dup-sequential` | 500 / 500 | same request_id sent again at the same instant, or 50 ms–1 s later |
| `--replay-after` | 50 | replays after the sale is over (about 80% aimed at actual winners, the rest at losers) |
| `--new-rid` / `--rid-conflict` | 20 / 20 | a winner retrying with a new request_id; a winner's request_id sent by a different user |
| `--expect-allocator` | – | refuse to run unless the seller reports this allocator |
| `--seed` | 1 | makes the schedule reproducible |
| `--processes` | 4 | worker processes sharing the stampede (one start time; each owns every P-th request) |
| `--max-inflight` | 2000 | cap on in-flight requests per process; waiting for a free slot is counted as client send lag, not hidden |
| `--concurrency` | – | switch to **closed-loop** with this many in-flight requests (only for the C4 comparison) |
| `--audit-interval` | 0.1 | seconds between live `/status` audits during the sale; 0 disables |
| `--retry-unknown` / `--retry-rate` | 0 / 0 | retry 503s and timeouts up to N times with the same request_id; cap retries at R/s across the client (over-budget retries wait) |
| `--stall-at` / `--stall-for` / `--stall-latency-ms` | – / 10 / 3000 | make Postgres slow via toxiproxy at t=X s for Y s (needs the seller started with `DB_HOST=toxiproxy DB_PORT=5433`) |

The run has two phases. First the **stampede**, which is timed: it's sent on a fixed schedule and never waits for responses. Then the **probes**: replays, new request_ids and conflicts, aimed at the buyers who *actually* won or lost in phase 1. The probes are verified but not timed.

Every report ends with **client health**: each worker's CPU use and the client's send lag. If a worker is near 100% of a core, or the send lag grows, the client (not the seller) was the limit, and that run's numbers are suspect.

Manual poking: seller1 is on `http://localhost:8001` and the load balancer over seller1–3 on `http://localhost:8080` (if that port is busy, set `SELLER1_PORT`, e.g. `SELLER1_PORT=18001 docker compose up -d`).
```bash
curl -X POST localhost:8001/reset -H 'content-type: application/json' -d '{"count":100}'
curl -X POST localhost:8001/buy   -H 'content-type: application/json' -d '{"user_id":"alice","request_id":"r1"}'
curl localhost:8001/status
```
Clean up with `docker compose down -v`.

## Responses
| HTTP | body | meaning |
|---|---|---|
| 200 | `{"status":"purchased","ticket_no":7,"epoch":3,"replayed":false,"existing":false}` | You hold ticket 7. `replayed`: this request_id was seen before. `existing`: this user already held a ticket. |
| 409 | `{"status":"sold_out","epoch":3}` | Definitively sold out. |
| 422 | `{"status":"request_id_conflict"}` | This request_id belongs to a different user. |
| 503 | `{"status":"unknown","retry_with_same_request_id":true}` | A statement was sent and no answer came back: **maybe** bought. Retrying with the same request_id is safe, and finds the ticket if it committed. |
| 503 | `{"status":"not_attempted","retry":true}` | Nothing was sent to the database (no connection, or shed by `MAX_INFLIGHT`): **definitely not** bought. Retry later. |

## What the buyer checks
| id | check |
|---|---|
| I1 | Never sell more tickets than exist: from `/status` **and** from the tickets actually confirmed to buyers |
| I2 | No ticket number issued twice, in `/status` or across confirmations |
| I3 | A repeated request_id never yields a second ticket |
| I4 | `/status` `sold` equals its holder list, and every ticket confirmed to a buyer appears in it (no lost sales) |
| U1–U5 | One ticket per user; a winner's request_id reused by someone else is rejected; no false "sold out"; no responses from a different sale; **a ticket holder is never told "sold out"** |
| A3 | **Live audit**: `/status` is polled during the sale, and every snapshot must be consistent (count = list, no duplicates, no oversell). Within one sale, no ticket may disappear and the count may never go down. |
| A2 | Orphaned tickets: sold, but the buyer was never told (reported as a count, not pass/fail) |

## Status
| Milestone | State |
|---|---|
| M1: the naive seller gets caught | done |
| M2: the safe seller passes | done |
| M3: a buyer we can trust at scale | done |
| M4: choosing the allocation strategy from evidence | done |
| M5: how much load, and where is the bottleneck | done: [results/M5-bottleneck.md](results/M5-bottleneck.md) |
| M6: the datastore goes slow for 10 s | done: [results/M6-slowdb.md](results/M6-slowdb.md) |
| M7: kill the datastore mid-sale (TF2) | done: [results/M7-killdb.md](results/M7-killdb.md) |
| M8: three instances behind nginx (TF1) | done: [results/M8-tf1.md](results/M8-tf1.md) |
| M10: write-up and clean-machine check | next |
