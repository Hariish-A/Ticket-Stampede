# Run `sweep-2000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T09:17:01+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 7846 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 431 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 24405 responses in 22.056 s → **1106.5 req/s** handled; 5595 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1059.3 | 5698.9 | 10417.4 | 10976.8 |
| service time (from actual send) | 1053.8 | 5694.5 | 10417.0 | 10976.0 |
| client send lag | 0.7 | 1.3 | 126.3 | 221.2 |
| ↳ seller: waiting for a DB connection | 0.0 | 943.2 | 997.5 | 1001.9 |
| ↳ seller: allocator queries | 13.2 | 51.7 | 269.9 | 534.7 |
| ↳ seller: whole handler | 1010.5 | 1120.7 | 1258.9 | 1325.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 29.8 | 5639.8 | 10307.9 | 10903.0 |

Responses by HTTP status: `{'0': 5595, '200': 100, '409': 7836, '503': 16469}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'TimeoutError': 5595}`  
First sold-out answer at t = 0.134 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 12744, 'sold_out_checks': 12744}`  
Client health: 4 worker processes, CPU per worker `['25%', '25%', '24%', '24%']` of one core; send lag p99 126.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
