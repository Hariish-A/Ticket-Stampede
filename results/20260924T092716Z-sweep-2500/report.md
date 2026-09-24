# Run `sweep-2500`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 37500 requests (burst 0 at t=0, then 2500.0/s) · seed 1 · 2026-09-24T09:27:16+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 15321 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 541 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 31288 responses in 22.436 s → **1394.5 req/s** handled; 6212 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1597.1 | 7014.3 | 10997.7 | 11626.3 |
| service time (from actual send) | 1071.7 | 5779.8 | 9992.6 | 10972.0 |
| client send lag | 1.3 | 1412.6 | 1633.5 | 1809.4 |
| ↳ seller: waiting for a DB connection | 0.0 | 892.1 | 996.7 | 1004.5 |
| ↳ seller: allocator queries | 3.8 | 11.9 | 58.3 | 245.4 |
| ↳ seller: whole handler | 1003.0 | 1107.0 | 1197.1 | 1256.1 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 38.8 | 5771.0 | 9984.3 | 10964.7 |

Responses by HTTP status: `{'0': 6212, '200': 100, '409': 15311, '503': 15877}`  
Requests by kind: `{'fresh': 37500}`  
Transport errors: `{'TimeoutError': 6212}`  
First sold-out answer at t = 0.122 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 3, 'sold_out_checks': 3, 'sold_out_fast': 20435}`  
Client health: 4 worker processes, CPU per worker `['24%', '24%', '24%', '24%']` of one core; send lag p99 1633.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
