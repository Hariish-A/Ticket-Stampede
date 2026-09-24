# Run `hotrow-skiplocked-sync-on`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:35:12+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 13853 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 553 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 368 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.845 s → **1114.4 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.4 | 1124.5 | 3847.7 | 4636.5 |
| service time (from actual send) | 1.6 | 1113.5 | 3842.6 | 4635.5 |
| client send lag | 0.7 | 9.4 | 30.5 | 163.4 |
| ↳ seller: waiting for a DB connection | 0.0 | 515.8 | 814.9 | 999.6 |
| ↳ seller: allocator queries | 0.4 | 11.0 | 21.6 | 337.0 |
| ↳ seller: whole handler | 0.9 | 856.3 | 1010.4 | 1115.4 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 288.9 | 3688.1 | 3877.1 |

Responses by HTTP status: `{'200': 5201, '409': 13843, '503': 1956}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 5.034 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 41, 'blocking_fallbacks': 10, 'sold_out_checks': 10, 'sold_out_fast': 13843}`  
Client health: 4 worker processes, CPU per worker `['14%', '14%', '14%', '14%']` of one core; send lag p99 30.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
