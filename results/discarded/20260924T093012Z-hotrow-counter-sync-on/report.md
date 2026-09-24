# Run `hotrow-counter-sync-on`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:30:12+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 4787 confirmed, 4787 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=4787 = 4787 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 4787/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 546 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 435 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 19.168 s → **1095.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1008.6 | 1577.0 | 2127.3 | 2504.3 |
| service time (from actual send) | 1007.9 | 1558.7 | 2126.6 | 2503.3 |
| client send lag | 0.7 | 9.6 | 31.4 | 168.3 |
| ↳ seller: waiting for a DB connection | 998.5 | 999.5 | 999.9 | 1002.0 |
| ↳ seller: allocator queries | 59.3 | 156.8 | 310.5 | 598.4 |
| ↳ seller: whole handler | 1001.4 | 1095.0 | 1204.0 | 1665.9 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.7 | 477.4 | 1137.0 | 1495.9 |

Responses by HTTP status: `{'200': 4841, '503': 16159}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 4787, 'unique_violation_retries': 33}`  
Client health: 4 worker processes, CPU per worker `['16%', '16%', '16%', '16%']` of one core; send lag p99 31.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
