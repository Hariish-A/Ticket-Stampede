# Run `hotrow-skiplocked-sync-on`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T09:31:07+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 5000 confirmed, 5000 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=5000 = 5000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 13981 sold-out answers, 5000/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 548 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 358 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 18.83 s → **1115.3 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.5 | 1333.9 | 2691.8 | 3206.5 |
| service time (from actual send) | 1.6 | 1320.1 | 2682.6 | 3206.1 |
| client send lag | 0.7 | 8.9 | 31.6 | 186.7 |
| ↳ seller: waiting for a DB connection | 0.0 | 455.3 | 920.1 | 995.1 |
| ↳ seller: allocator queries | 0.4 | 9.7 | 16.2 | 556.7 |
| ↳ seller: whole handler | 0.9 | 886.4 | 1048.9 | 1172.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 381.5 | 2223.4 | 2318.5 |

Responses by HTTP status: `{'200': 5195, '409': 13971, '503': 1834}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = 4.713 s  
Seller counters during the run (GET /metrics): `{'claims': 5000, 'unique_violation_retries': 45, 'blocking_fallbacks': 4, 'sold_out_checks': 4, 'sold_out_fast': 13977}`  
Client health: 4 worker processes, CPU per worker `['14%', '14%', '14%', '14%']` of one core; send lag p99 31.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
