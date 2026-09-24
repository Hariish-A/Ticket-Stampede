# Run `sweep-3000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 45000 requests (burst 0 at t=0, then 3000.0/s) · seed 1 · 2026-09-24T09:18:03+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 6837 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 433 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 32617 responses in 27.467 s → **1187.5 req/s** handled; 12383 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 4481.5 | 7073.7 | 13588.0 | 14868.6 |
| service time (from actual send) | 1124.8 | 1425.0 | 9128.5 | 10575.8 |
| client send lag | 3147.4 | 5367.6 | 6705.1 | 7129.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 963.7 | 998.5 | 1002.7 |
| ↳ seller: allocator queries | 17.8 | 62.4 | 428.2 | 1072.1 |
| ↳ seller: whole handler | 1032.1 | 1194.7 | 1333.8 | 1938.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 59.6 | 286.8 | 9022.8 | 10341.4 |

Responses by HTTP status: `{'0': 12383, '200': 100, '409': 6827, '503': 25690}`  
Requests by kind: `{'fresh': 45000}`  
Transport errors: `{'TimeoutError': 11977, 'ClientOSError': 406}`  
First sold-out answer at t = 0.136 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 12477, 'sold_out_checks': 12477}`  
Client health: 4 worker processes, CPU per worker `['22%', '23%', '22%', '22%']` of one core; send lag p99 6705.1 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
