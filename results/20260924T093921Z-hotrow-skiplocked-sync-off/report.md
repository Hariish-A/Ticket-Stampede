# Run `hotrow-skiplocked-sync-off`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:39:21+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 13949 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 560 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 360 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.842 s → **1114.5 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.3 | 1498.7 | 2150.5 | 2609.2 |
| service time (from actual send) | 1.5 | 1475.6 | 2149.6 | 2608.3 |
| client send lag | 0.7 | 9.7 | 31.9 | 182.5 |
| ↳ seller: waiting for a DB connection | 0.0 | 15.1 | 825.5 | 996.3 |
| ↳ seller: allocator queries | 0.4 | 5.2 | 10.4 | 431.2 |
| ↳ seller: whole handler | 0.8 | 803.8 | 1090.8 | 1303.1 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 428.2 | 2085.3 | 2277.7 |

Responses by HTTP status: `{'200': 5222, '409': 13939, '503': 1839}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 4.737 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 55, 'sold_out_fast': 13949}`  
Client health: 4 worker processes, CPU per worker `['13%', '13%', '13%', '13%']` of one core; send lag p99 31.9 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
