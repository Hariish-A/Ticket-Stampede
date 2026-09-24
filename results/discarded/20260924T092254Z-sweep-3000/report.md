# Run `sweep-3000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 45000 requests (burst 0 at t=0, then 3000.0/s) · seed 1 · 2026-09-24T09:22:54+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 15475 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 533 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 35723 responses in 25.751 s → **1387.3 req/s** handled; 9277 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3505.3 | 6265.4 | 13241.2 | 14032.6 |
| service time (from actual send) | 1071.1 | 6264.3 | 10413.4 | 10928.5 |
| client send lag | 2000.6 | 3276.4 | 4691.3 | 4857.1 |
| ↳ seller: waiting for a DB connection | 0.0 | 926.4 | 995.0 | 1003.1 |
| ↳ seller: allocator queries | 4.4 | 13.4 | 63.1 | 248.8 |
| ↳ seller: whole handler | 1006.2 | 1110.7 | 1261.6 | 1465.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 39.1 | 6014.4 | 10407.6 | 10923.5 |

Responses by HTTP status: `{'0': 9277, '200': 100, '409': 15465, '503': 20158}`  
Requests by kind: `{'fresh': 45000}`  
Transport errors: `{'TimeoutError': 9277}`  
First sold-out answer at t = 0.146 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 9, 'sold_out_fast': 21038, 'sold_out_checks': 9}`  
Client health: 4 worker processes, CPU per worker `['24%', '24%', '24%', '24%']` of one core; send lag p99 4691.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
