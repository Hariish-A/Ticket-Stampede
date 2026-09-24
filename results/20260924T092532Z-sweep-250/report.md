# Run `sweep-250`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 3750 requests (burst 0 at t=0, then 250.0/s) · seed 1 · 2026-09-24T09:25:32+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 3660 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 536 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 3750 responses in 14.997 s → **250.0 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.8 | 4.2 | 6.4 | 19.5 |
| service time (from actual send) | 1.8 | 2.6 | 5.6 | 16.9 |
| client send lag | 1.0 | 1.8 | 2.2 | 3.9 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 0.1 | 0.2 |
| ↳ seller: allocator queries | 0.5 | 0.7 | 3.8 | 5.5 |
| ↳ seller: whole handler | 0.8 | 1.2 | 4.4 | 6.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.0 | 1.3 | 1.8 | 11.6 |

Responses by HTTP status: `{'200': 100, '409': 3650}`  
Requests by kind: `{'fresh': 3750}`  
First sold-out answer at t = 0.406 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'sold_out_fast': 3660}`  
Client health: 4 worker processes, CPU per worker `['5%', '5%', '5%', '5%']` of one core; send lag p99 2.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
