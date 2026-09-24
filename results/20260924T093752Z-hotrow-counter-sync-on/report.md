# Run `hotrow-counter-sync-on`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:37:52+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 4882 confirmed, 4882 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=4882 = 4882 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 4882/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 557 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 409 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 19.211 s → **1093.1 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1007.6 | 1518.1 | 1895.1 | 2037.4 |
| service time (from actual send) | 1006.9 | 1497.7 | 1868.6 | 2013.4 |
| client send lag | 0.7 | 10.0 | 31.7 | 154.7 |
| ↳ seller: waiting for a DB connection | 998.5 | 999.5 | 999.9 | 1002.5 |
| ↳ seller: allocator queries | 60.2 | 155.0 | 288.4 | 592.0 |
| ↳ seller: whole handler | 1001.2 | 1089.0 | 1199.0 | 1610.0 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.5 | 458.7 | 869.6 | 962.3 |

Responses by HTTP status: `{'200': 4938, '503': 16062}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 4882, 'unique_violation_retries': 34}`  
Client health: 4 worker processes, CPU per worker `['16%', '15%', '15%', '15%']` of one core; send lag p99 31.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
