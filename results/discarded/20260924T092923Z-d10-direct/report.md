# Run `d10-direct`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 12000 requests (burst 0 at t=0, then 800.0/s) · seed 1 · 2026-09-24T09:29:23+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 11910 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 544 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 12000 responses in 15.005 s → **799.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1.9 | 2.7 | 292.8 | 342.5 |
| service time (from actual send) | 1.2 | 1.8 | 291.9 | 341.8 |
| client send lag | 0.7 | 1.1 | 1.2 | 22.3 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 5.5 | 227.5 |
| ↳ seller: allocator queries | 0.3 | 0.5 | 8.0 | 175.9 |
| ↳ seller: whole handler | 0.5 | 1.0 | 27.0 | 307.9 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.6 | 0.9 | 274.5 | 304.6 |

Responses by HTTP status: `{'200': 100, '409': 11900}`  
Requests by kind: `{'fresh': 12000}`  
First sold-out answer at t = 0.38 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 11, 'sold_out_checks': 11, 'sold_out_fast': 11899}`  
Client health: 4 worker processes, CPU per worker `['9%', '9%', '9%', '9%']` of one core; send lag p99 1.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
