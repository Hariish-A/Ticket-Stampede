# Run `sweep-2500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 37500 requests (burst 0 at t=0, then 2500.0/s) · seed 1 · 2026-09-24T09:22:25+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 15144 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 532 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 31037 responses in 23.035 s → **1347.4 req/s** handled; 6463 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1727.8 | 7261.5 | 11235.8 | 11822.0 |
| service time (from actual send) | 1082.2 | 6068.6 | 9884.3 | 10505.0 |
| client send lag | 63.5 | 1370.1 | 1717.1 | 1807.1 |
| ↳ seller: waiting for a DB connection | 0.0 | 908.8 | 995.1 | 1005.2 |
| ↳ seller: allocator queries | 3.6 | 12.0 | 64.7 | 258.5 |
| ↳ seller: whole handler | 1003.6 | 1088.8 | 1189.7 | 1328.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 45.6 | 6061.9 | 9873.0 | 10501.3 |

Responses by HTTP status: `{'0': 6463, '200': 100, '409': 15134, '503': 15803}`  
Requests by kind: `{'fresh': 37500}`  
Transport errors: `{'TimeoutError': 6463}`  
First sold-out answer at t = 0.219 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2, 'sold_out_fast': 20357, 'sold_out_checks': 2}`  
Client health: 4 worker processes, CPU per worker `['24%', '24%', '24%', '24%']` of one core; send lag p99 1717.1 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
