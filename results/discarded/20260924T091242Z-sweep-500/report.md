# Run `sweep-500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 2500 requests (burst 0 at t=0, then 500.0/s) · seed 1 · 2026-09-24T09:12:42+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 2410 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 424 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 2500 responses in 5.003 s → **499.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.6 | 26.6 | 316.8 | 364.8 |
| service time (from actual send) | 2.8 | 25.6 | 315.7 | 362.3 |
| client send lag | 0.7 | 1.1 | 1.3 | 6.4 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 12.2 | 233.5 |
| ↳ seller: allocator queries | 1.4 | 7.6 | 51.5 | 175.4 |
| ↳ seller: whole handler | 1.9 | 12.4 | 154.7 | 342.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.0 | 4.0 | 286.8 | 299.2 |

Responses by HTTP status: `{'200': 100, '409': 2400}`  
Requests by kind: `{'fresh': 2500}`  
First sold-out answer at t = 0.428 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2410, 'sold_out_checks': 2410}`  
Client health: 4 worker processes, CPU per worker `['9%', '9%', '9%', '9%']` of one core; send lag p99 1.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
