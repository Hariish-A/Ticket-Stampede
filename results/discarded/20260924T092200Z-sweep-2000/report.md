# Run `sweep-2000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T09:22:00+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 14140 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 531 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 28641 responses in 18.955 s → **1511.0 req/s** handled; 1359 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1050.8 | 5430.9 | 9613.3 | 10992.7 |
| service time (from actual send) | 1049.8 | 5430.0 | 9612.6 | 10992.3 |
| client send lag | 0.7 | 1.1 | 12.6 | 96.9 |
| ↳ seller: waiting for a DB connection | 0.0 | 911.8 | 997.1 | 1074.7 |
| ↳ seller: allocator queries | 3.9 | 12.4 | 76.5 | 314.1 |
| ↳ seller: whole handler | 1003.0 | 1132.0 | 1310.8 | 1580.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 31.7 | 5425.1 | 9607.4 | 10989.0 |

Responses by HTTP status: `{'0': 1359, '200': 100, '409': 14130, '503': 14411}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'TimeoutError': 1359}`  
First sold-out answer at t = 0.118 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 7, 'sold_out_fast': 15480, 'sold_out_checks': 7}`  
Client health: 4 worker processes, CPU per worker `['27%', '27%', '28%', '27%']` of one core; send lag p99 12.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
