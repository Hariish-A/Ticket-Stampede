# Run `hotrow-counter-sync-off`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:34:43+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 2751 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 552 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 407 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.856 s → **1113.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1004.6 | 1414.8 | 1808.0 | 2012.2 |
| service time (from actual send) | 1003.8 | 1410.6 | 1803.5 | 2011.1 |
| client send lag | 0.7 | 9.0 | 33.1 | 184.0 |
| ↳ seller: waiting for a DB connection | 939.8 | 999.3 | 999.9 | 1002.9 |
| ↳ seller: allocator queries | 6.5 | 108.8 | 241.5 | 433.1 |
| ↳ seller: whole handler | 1000.6 | 1088.9 | 1181.5 | 1584.0 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.7 | 396.0 | 877.9 | 947.2 |

Responses by HTTP status: `{'200': 5089, '409': 2741, '503': 13170}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 16.297 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 39, 'sold_out_fast': 2732, 'sold_out_checks': 19}`  
Client health: 4 worker processes, CPU per worker `['16%', '16%', '16%', '16%']` of one core; send lag p99 33.1 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
