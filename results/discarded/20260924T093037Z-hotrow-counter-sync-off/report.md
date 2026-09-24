# Run `hotrow-counter-sync-off`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:30:37+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 4723 confirmed, 4723 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=4723 = 4723 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 4723/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 547 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 404 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 19.113 s → **1098.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1007.5 | 1408.1 | 1701.8 | 2006.4 |
| service time (from actual send) | 1006.9 | 1391.5 | 1682.8 | 1991.8 |
| client send lag | 0.7 | 9.3 | 43.1 | 215.5 |
| ↳ seller: waiting for a DB connection | 998.5 | 999.5 | 999.9 | 1096.3 |
| ↳ seller: allocator queries | 60.9 | 162.8 | 323.1 | 546.8 |
| ↳ seller: whole handler | 1001.0 | 1095.2 | 1209.8 | 1642.3 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.5 | 351.5 | 609.2 | 796.8 |

Responses by HTTP status: `{'200': 4763, '503': 16237}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 4723, 'unique_violation_retries': 23}`  
Client health: 4 worker processes, CPU per worker `['15%', '16%', '16%', '16%']` of one core; send lag p99 43.1 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
