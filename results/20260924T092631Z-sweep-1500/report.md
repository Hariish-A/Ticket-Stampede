# Run `sweep-1500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 22500 requests (burst 0 at t=0, then 1500.0/s) · seed 1 · 2026-09-24T09:26:31+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 22408 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 539 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 22500 responses in 15.195 s → **1480.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 4.7 | 108.3 | 521.6 | 1007.4 |
| service time (from actual send) | 4.0 | 107.3 | 511.8 | 1006.8 |
| client send lag | 0.7 | 1.1 | 1.4 | 46.1 |
| ↳ seller: waiting for a DB connection | 0.0 | 50.6 | 463.2 | 958.5 |
| ↳ seller: allocator queries | 0.9 | 5.5 | 11.3 | 87.2 |
| ↳ seller: whole handler | 2.7 | 69.1 | 477.8 | 1002.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.4 | 8.1 | 315.1 | 393.3 |

Responses by HTTP status: `{'200': 100, '409': 22398, '503': 2}`  
Requests by kind: `{'fresh': 22500}`  
First sold-out answer at t = 0.122 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 6, 'sold_out_checks': 6, 'sold_out_fast': 22402}`  
Client health: 4 worker processes, CPU per worker `['22%', '22%', '22%', '22%']` of one core; send lag p99 1.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
