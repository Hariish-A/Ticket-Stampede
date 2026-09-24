# Ticket Stampede

A ticket seller that must sell exactly N tickets to a stampede of buyers without ever overselling, plus the load client that attacks it and checks the result.

- **Seller** (`seller/`): FastAPI + asyncpg on Postgres 16. Endpoints: `POST /reset`, `POST /buy`, `GET /status`. The allocator is chosen with `ALLOCATOR=skiplocked|naive`, and the default is `skiplocked`. The invariants are enforced by Postgres constraints ([schema.sql](seller/schema.sql)); the claim is a single `UPDATE … FOR UPDATE SKIP LOCKED` ([skiplocked.py](seller/app/allocators/skiplocked.py)).
- **Buyer** (`buyer/`): an open-loop load client. It fires a scheduled stampede with duplicate and replayed request ids, then verifies the four invariants against `/status` **and** against its own record of what each buyer was told.

Design and trade-offs: [DECISIONS.md](DECISIONS.md) (written at M10). The working plan is in [Plan.md](Plan.md), and progress in [Progress.md](Progress.md).

## Requirements
- Docker with Compose v2 (Docker Desktop on Windows or macOS). Nothing else; Python runs inside the containers.
- A bash shell for `scripts/` (Git Bash on Windows works).

## Run it (about 2 minutes)
```bash
git clone <this repo> && cd ticket-stampede

./scripts/test.sh      # 22 buyer unit tests + 11 seller integration tests against real Postgres
./scripts/c1.sh        # the same 51,000-request stampede against the naive seller (FAILs) and the safe one (PASSes)
./scripts/naive.sh     # just the naive seller
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
| `--replay-after` | 50 | early (likely winning) requests replayed after the sale is over |
| `--new-rid` / `--rid-conflict` | 20 / 20 | a winner retrying with a new request_id; a winner's request_id sent by a different user |
| `--expect-allocator` | – | refuse to run unless the seller reports this allocator |

The run has two phases. First the **stampede**, which is timed: it's sent on a fixed schedule and never waits for responses. Then the **probes**: replays, new request_ids and conflicts, aimed at the buyers who *actually* won or lost in phase 1. The probes are verified but not timed.
| `--seed` | 1 | makes the schedule reproducible |

Manual poking: the seller is on `http://localhost:8001` (if that port is busy, set `SELLER1_PORT`, e.g. `SELLER1_PORT=18001 docker compose up -d`).
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
| 503 | `{"status":"unknown","retry_with_same_request_id":true}` | The datastore didn't give a definite answer. Retrying with the same request_id is safe. |

## What the buyer checks
| id | check |
|---|---|
| I1 | Never sell more tickets than exist: from `/status` **and** from the tickets actually confirmed to buyers |
| I2 | No ticket number issued twice, in `/status` or across confirmations |
| I3 | A repeated request_id never yields a second ticket |
| I4 | `/status` `sold` equals its holder list, and every ticket confirmed to a buyer appears in it (no lost sales) |
| U1–U5 | One ticket per user; a winner's request_id reused by someone else is rejected; no false "sold out"; no responses from a different sale; **a ticket holder is never told "sold out"** |
| A2 | Orphaned tickets: sold, but the buyer was never told (reported as a count, not pass/fail) |

## Status
| Milestone | State |
|---|---|
| M1: the naive seller gets caught | done |
| M2: the safe seller passes | done |
| M3: a buyer we can trust at scale | next |
