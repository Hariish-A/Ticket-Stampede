# Run `sweep-3000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 45000 requests (burst 0 at t=0, then 3000.0/s) · seed 1 · 2026-09-24T09:27:45+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 14730 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 542 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 35127 responses in 25.523 s → **1376.3 req/s** handled; 9873 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3802.2 | 5778.3 | 13591.0 | 14099.9 |
| service time (from actual send) | 1061.2 | 3724.7 | 10482.6 | 10939.0 |
| client send lag | 2457.3 | 3742.0 | 4842.4 | 5080.5 |
| ↳ seller: waiting for a DB connection | 0.0 | 917.7 | 996.5 | 1006.8 |
| ↳ seller: allocator queries | 4.9 | 14.8 | 65.6 | 298.8 |
| ↳ seller: whole handler | 1008.1 | 1090.3 | 1196.8 | 1469.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 38.4 | 3652.5 | 10479.2 | 10935.7 |

Responses by HTTP status: `{'0': 9873, '200': 100, '409': 14720, '503': 20307}`  
Requests by kind: `{'fresh': 45000}`  
Transport errors: `{'TimeoutError': 9873}`  
First sold-out answer at t = 0.178 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2, 'sold_out_checks': 2, 'sold_out_fast': 20479}`  
Client health: 4 worker processes, CPU per worker `['24%', '24%', '24%', '24%']` of one core; send lag p99 4842.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
