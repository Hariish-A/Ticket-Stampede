# Run `sweep-4000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 60000 requests (burst 0 at t=0, then 4000.0/s) · seed 1 · 2026-09-24T09:18:37+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 11033 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 434 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 43430 responses in 36.588 s → **1187.0 req/s** handled; 16570 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 7100.1 | 14063.5 | 21262.7 | 23531.4 |
| service time (from actual send) | 1118.2 | 2199.3 | 9975.3 | 10948.3 |
| client send lag | 5430.8 | 11602.5 | 14526.3 | 14732.8 |
| ↳ seller: waiting for a DB connection | 0.0 | 944.6 | 995.9 | 1000.8 |
| ↳ seller: allocator queries | 13.9 | 51.0 | 370.1 | 937.9 |
| ↳ seller: whole handler | 1023.2 | 1167.9 | 1271.6 | 2198.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 59.0 | 1341.0 | 9961.5 | 10940.2 |

Responses by HTTP status: `{'0': 16570, '200': 100, '409': 11023, '503': 32307}`  
Requests by kind: `{'fresh': 60000}`  
Transport errors: `{'TimeoutError': 16027, 'ClientOSError': 543}`  
First sold-out answer at t = 0.137 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 18194, 'sold_out_checks': 18194}`  
Client health: 4 worker processes, CPU per worker `['24%', '25%', '28%', '27%']` of one core; send lag p99 14526.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
