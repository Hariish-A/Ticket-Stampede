# Run `sweep-500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 7500 requests (burst 0 at t=0, then 500.0/s) · seed 1 · 2026-09-24T09:25:51+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 7410 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 537 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 7500 responses in 15.001 s → **500.0 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.4 | 3.2 | 6.8 | 19.4 |
| service time (from actual send) | 1.6 | 2.3 | 6.2 | 17.9 |
| client send lag | 0.7 | 1.1 | 1.3 | 2.6 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 0.1 | 0.4 |
| ↳ seller: allocator queries | 0.4 | 0.6 | 4.3 | 15.0 |
| ↳ seller: whole handler | 0.7 | 1.1 | 5.1 | 16.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.9 | 1.2 | 1.6 | 11.1 |

Responses by HTTP status: `{'200': 100, '409': 7400}`  
Requests by kind: `{'fresh': 7500}`  
First sold-out answer at t = 0.208 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2, 'sold_out_checks': 2, 'sold_out_fast': 7408}`  
Client health: 4 worker processes, CPU per worker `['8%', '8%', '8%', '8%']` of one core; send lag p99 1.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
