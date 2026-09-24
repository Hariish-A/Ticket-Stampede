# Run `hotrow-counter-sync-off`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:38:21+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 15200 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 558 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 336 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.839 s → **1114.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.5 | 1169.0 | 3051.4 | 3250.0 |
| service time (from actual send) | 1.7 | 1154.8 | 3050.3 | 3249.7 |
| client send lag | 0.7 | 9.0 | 29.5 | 156.8 |
| ↳ seller: waiting for a DB connection | 0.0 | 25.1 | 739.5 | 998.8 |
| ↳ seller: allocator queries | 0.6 | 6.2 | 11.1 | 452.0 |
| ↳ seller: whole handler | 1.0 | 142.4 | 1009.2 | 1041.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 342.5 | 3037.2 | 3240.9 |

Responses by HTTP status: `{'200': 5242, '409': 15190, '503': 568}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 3.763 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 45, 'sold_out_checks': 5, 'sold_out_fast': 15195}`  
Client health: 4 worker processes, CPU per worker `['14%', '14%', '13%', '13%']` of one core; send lag p99 29.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
