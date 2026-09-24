# Run `sweep-2500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 37500 requests (burst 0 at t=0, then 2500.0/s) · seed 1 · 2026-09-24T09:17:29+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 9552 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 432 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 28632 responses in 26.947 s → **1062.5 req/s** handled; 8868 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2550.2 | 9240.6 | 12286.4 | 13276.0 |
| service time (from actual send) | 1094.1 | 7838.7 | 10653.6 | 10954.9 |
| client send lag | 1182.9 | 1994.3 | 2315.2 | 2516.4 |
| ↳ seller: waiting for a DB connection | 0.0 | 908.2 | 997.6 | 1006.0 |
| ↳ seller: allocator queries | 11.5 | 44.3 | 275.5 | 584.5 |
| ↳ seller: whole handler | 1012.0 | 1110.0 | 1235.4 | 1494.1 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 49.1 | 7747.4 | 10642.0 | 10945.1 |

Responses by HTTP status: `{'0': 8868, '200': 100, '409': 9542, '503': 18990}`  
Requests by kind: `{'fresh': 37500}`  
Transport errors: `{'TimeoutError': 8868}`  
First sold-out answer at t = 0.107 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 16266, 'sold_out_checks': 16254}`  
Client health: 4 worker processes, CPU per worker `['21%', '21%', '20%', '20%']` of one core; send lag p99 2315.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
