# Run `c2-brief-counter`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T08:47:55+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 49835 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 329 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 64 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 477 snapshots over 52.0s, 0 violations (1 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.63 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.9 | 23.2 | 1430.5 | 1702.3 |
| service time (from actual send) | 2.1 | 22.4 | 1415.1 | 1698.5 |
| client send lag | 0.7 | 1.1 | 14.4 | 121.5 |

Responses by HTTP status: `{'200': 100, '409': 49825, '503': 1075}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.936 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'sold_out_checks': 49835}`  
Client health: 4 worker processes, CPU per worker `['12%', '12%', '12%', '12%']` of one core; send lag p99 14.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
