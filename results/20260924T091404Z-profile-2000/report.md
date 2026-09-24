# Run `profile-2000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 50000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T09:14:04+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 10594 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 426 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 44193 responses in 29.582 s → **1493.9 req/s** handled; 5807 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1089.5 | 1291.3 | 8964.9 | 10535.4 |
| service time (from actual send) | 1088.5 | 1290.2 | 8964.2 | 10534.7 |
| client send lag | 0.7 | 1.1 | 13.7 | 89.8 |
| ↳ seller: waiting for a DB connection | 0.0 | 963.0 | 999.1 | 1055.0 |
| ↳ seller: allocator queries | 13.4 | 45.7 | 301.8 | 851.9 |
| ↳ seller: whole handler | 1014.7 | 1149.3 | 1252.6 | 1415.9 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 31.1 | 180.6 | 8657.7 | 10526.7 |

Responses by HTTP status: `{'0': 5807, '200': 100, '409': 10584, '503': 33509}`  
Requests by kind: `{'fresh': 50000}`  
Transport errors: `{'TimeoutError': 5807}`  
First sold-out answer at t = 0.403 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 15592, 'sold_out_checks': 15592}`  
Client health: 4 worker processes, CPU per worker `['24%', '23%', '22%', '23%']` of one core; send lag p99 13.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
