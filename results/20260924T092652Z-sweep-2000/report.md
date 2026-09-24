# Run `sweep-2000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T09:26:52+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 14278 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 540 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 28599 responses in 18.827 s → **1519.1 req/s** handled; 1401 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1043.8 | 6017.7 | 10218.3 | 10505.8 |
| service time (from actual send) | 1043.0 | 6017.4 | 10217.6 | 10504.9 |
| client send lag | 0.7 | 1.1 | 11.0 | 75.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 939.1 | 998.9 | 1099.9 |
| ↳ seller: allocator queries | 4.1 | 12.6 | 60.9 | 320.2 |
| ↳ seller: whole handler | 1002.8 | 1106.9 | 1259.2 | 1754.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 28.1 | 6011.4 | 10213.5 | 10501.4 |

Responses by HTTP status: `{'0': 1401, '200': 100, '409': 14268, '503': 14231}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'TimeoutError': 1401}`  
First sold-out answer at t = 0.121 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 14, 'sold_out_checks': 14, 'sold_out_fast': 15660}`  
Client health: 4 worker processes, CPU per worker `['27%', '27%', '27%', '28%']` of one core; send lag p99 11.0 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
