# Run `hotrow-counter-sync-on`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:34:19+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 3755 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 551 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 397 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.855 s → **1113.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1006.8 | 1449.7 | 2324.4 | 2532.4 |
| service time (from actual send) | 1006.1 | 1436.0 | 2269.1 | 2531.6 |
| client send lag | 0.7 | 10.1 | 38.2 | 198.9 |
| ↳ seller: waiting for a DB connection | 756.3 | 999.2 | 999.8 | 1033.8 |
| ↳ seller: allocator queries | 3.9 | 92.6 | 233.8 | 688.2 |
| ↳ seller: whole handler | 1000.9 | 1054.8 | 1190.3 | 1863.4 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 2.5 | 741.7 | 1293.8 | 1460.7 |

Responses by HTTP status: `{'200': 5080, '409': 3745, '503': 12175}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 15.375 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 30, 'sold_out_fast': 3736, 'sold_out_checks': 19}`  
Client health: 4 worker processes, CPU per worker `['16%', '16%', '16%', '16%']` of one core; send lag p99 38.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
