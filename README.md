# Ticket Stampede

A ticket seller that must sell exactly N tickets to a stampede of buyers without ever overselling, plus the load client that attacks it and checks the result.

- **Seller** (`seller/`): FastAPI + asyncpg on Postgres 16, with `POST /reset`, `POST /buy` and `GET /status`.
  - The invariants are enforced by Postgres constraints ([schema.sql](seller/schema.sql)). A purchase is one `UPDATE … FOR UPDATE SKIP LOCKED` ([skiplocked.py](seller/app/allocators/skiplocked.py)).
  - One instance, or three behind nginx (TF1).
- **Buyer** (`buyer/`): an open-loop load client. It fires a scheduled stampede, including duplicate, replayed and conflicting request ids. It then verifies the invariants against `/status` **and** against its own ledger of what every buyer was told.

**Read [DECISIONS.md](DECISIONS.md) first** (two pages: why it is built this way, how it was tested, where it breaks). Also:
- the milestone write-ups in `results/M*.md`;
- the plan and every decision in [Plan.md](Plan.md);
- the work log in [Progress.md](Progress.md);
- the AI session transcripts in [logs/](logs/).

## Requirements
- **Docker with Compose v2** (Docker Desktop on Windows or macOS, or Docker Engine on Linux). Python runs only inside containers.
- **A bash shell** for `scripts/`. On Windows, use Git Bash; line endings are pinned to LF by `.gitattributes`.
- **Free host ports 8001 and 8080.** If they're taken, set `SELLER1_PORT` or `LB_PORT`. Only used for manual `curl`.
- **Network access on the first run**, to pull images and install Python packages. pip is configured to tolerate slow networks.

## Run it in under 5 minutes
```bash
git clone https://github.com/Hariish-A/Ticket-Stampede.git && cd Ticket-Stampede
./scripts/test.sh   # builds the images, then 39 buyer unit tests + 34 seller integration tests against real Postgres
./scripts/c1.sh     # the same 51,000-request stampede against the naive seller (FAILs) and the safe one (PASSes)
```
**Measured** from a fresh clone of this repo with a fresh database volume: `test.sh` 34 s + `c1.sh` 126 s = **2 min 40 s**. That was with Docker's layer cache warm; see [Clean-checkout check](#clean-checkout-check) for a cold machine.

Each run prints its report and saves it to `results/<timestamp>-<scenario>/`: `report.md` and `report.json`, plus `ledger.jsonl` with every request (not committed). Clean up with `docker compose down -v`.

## Every experiment
| script | what it shows | time |
|---|---|---|
| `c1.sh` | naive vs safe seller under the same attack (the brief's failing run and passing run) | ~2.5 min |
| `calibrate.sh` | the client's own ceiling against nginx returning canned responses (TF4) | ~1 min |
| `c2.sh` | serializable vs counter vs skiplocked, at 100 and 5,000 tickets | ~7 min |
| `sweep.sh` | rate sweep with CPU + Postgres wait sampling: where the knee is, and why | ~5 min |
| `profile.sh`, `hotrow.sh`, `d10.sh` | py-spy + fsync rate; the hot-row ceiling (flush on/off); the client network path | ~2 min each |
| `slowdb.sh` | Postgres +3 s per answer for 10 s mid-sale: baseline, seller fail-fast, client retry budget, both, closed-loop | ~12 min |
| `killdb.sh` | SIGKILL Postgres mid-sale and restart it: 3 runs + a `synchronous_commit=off` control that must FAIL (TF2) | ~12 min |
| `tf1.sh` | the key scenarios against 3 sellers behind nginx (TF1); or `TOPOLOGY=tf1 ./scripts/<any>.sh` | ~25 min |

## Responses
| HTTP | body | meaning |
|---|---|---|
| 200 | `{"status":"purchased","ticket_no":7,"epoch":3,"replayed":false,"existing":false}` | You hold ticket 7. `replayed`: this request_id was seen before. `existing`: this user already held a ticket. |
| 409 | `{"status":"sold_out","epoch":3}` | Definitively sold out. |
| 422 | `{"status":"request_id_conflict"}` | This request_id belongs to a different user. |
| 503 | `{"status":"unknown","retry_with_same_request_id":true}` | A statement was sent and no answer came back: **maybe** bought. Retrying with the same request_id is safe, and finds the ticket if it committed. |
| 503 | `{"status":"not_attempted","retry":true}` | Nothing reached the database (no connection, or shed by `MAX_INFLIGHT`): **definitely not** bought. |

`/buy` never answers 500. `GET /metrics` exposes the allocator's counters; every `/buy` carries `Server-Timing` (pool wait, queries, handler).

Manual poking:
```bash
curl -X POST localhost:8001/reset -H 'content-type: application/json' -d '{"count":100}'
curl -X POST localhost:8001/buy   -H 'content-type: application/json' -d '{"user_id":"alice","request_id":"r1"}'
curl localhost:8001/status        # or localhost:8080 for the load balancer over seller1-3
```

## What the buyer checks
| id | check |
|---|---|
| I1 | Never sell more tickets than exist: in `/status` **and** in the tickets actually confirmed to buyers |
| I2 | No ticket number issued twice, in `/status` or across confirmations |
| I3 | A repeated request_id never yields a second ticket |
| I4 | `/status` `sold` equals its holder list, and every ticket confirmed to a buyer appears in it (no lost sales, "phantoms") |
| A3 | Live audit: `/status` polled during the sale; every snapshot consistent; within a sale no ticket disappears and the count never goes down |
| U1–U5 | One ticket per user; a winner's request_id reused by another user is never given a ticket; no false "sold out"; no responses from another sale; a ticket holder is never told "sold out" |
| A2 | Orphaned tickets: sold, but the buyer was never told (a count, not pass/fail) |

Buyer options: `docker compose run --rm buyer run --help`. The main ones:
- `--requests`, `--burst`, `--rate`, `--tickets`: the shape of the stampede.
- `--processes`: workers sharing the stampede.
- `--concurrency`: closed-loop mode, only for the C4 comparison.
- `--retry-unknown N`, `--retry-rate R`: retries with the same request_id, and a retry budget.
- `--stall-at` / `--stall-for`: make Postgres slow via toxiproxy.
- `--expect-allocator`: refuse to attack the wrong seller.

## Clean-checkout check
Run on 2026-09-27, Windows 11, Git Bash, Docker Desktop 27, from `git clone` of commit `04d0f9d` into an empty folder, after `docker compose down -v`:

| step | time | result |
|---|---|---|
| `./scripts/test.sh` | 34 s | 39 + 34 tests passed |
| `./scripts/c1.sh` | 126 s | naive FAIL (2,553 tickets for 100 seats), skiplocked PASS |

**A truly cold machine** also pulls `postgres:16-alpine`, `nginx:1.27-alpine`, `toxiproxy` and `python:3.12-slim`, and pip-installs three small requirement sets. That adds about 1–2 minutes on a normal connection. On a slow one it can take longer: in M10 PyPI answered in ~20 s, so pip has `--timeout 60 --retries 10`, and a failed build can simply be rerun. Dependencies are installed before code is copied, so only the first build pays this cost.

**Runs recorded before 2026-09-27 used `MAX_INFLIGHT=0`** (fail-fast off). From then on it is on at 64 by default ([D24](results/D24-failfast.md)). The reference C1 run with the shipped defaults: [naive](results/20260927T025823Z-c1-naive/report.md), [skiplocked](results/20260927T025924Z-c1-skiplocked/report.md).
