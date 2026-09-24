# Run `hotrow-skiplocked-sync-off`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:35:36+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 13670 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 554 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 361 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.849 s → **1114.1 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.4 | 1298.7 | 1684.8 | 2252.0 |
| service time (from actual send) | 1.6 | 1288.2 | 1674.2 | 2251.8 |
| client send lag | 0.7 | 10.0 | 32.5 | 186.1 |
| ↳ seller: waiting for a DB connection | 0.0 | 213.3 | 909.4 | 1000.6 |
| ↳ seller: allocator queries | 0.4 | 8.5 | 15.9 | 436.6 |
| ↳ seller: whole handler | 0.9 | 1000.6 | 1069.2 | 1249.7 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 410.9 | 1243.4 | 1433.2 |

Responses by HTTP status: `{'200': 5221, '409': 13660, '503': 2119}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 5.004 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 74, 'blocking_fallbacks': 4, 'sold_out_checks': 4, 'sold_out_fast': 13666}`  
Client health: 4 worker processes, CPU per worker `['13%', '13%', '13%', '13%']` of one core; send lag p99 32.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
