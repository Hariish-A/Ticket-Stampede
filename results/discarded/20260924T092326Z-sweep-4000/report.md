# Run `sweep-4000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 60000 requests (burst 0 at t=0, then 4000.0/s) · seed 1 · 2026-09-24T09:23:26+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 19607 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 534 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 45864 responses in 31.924 s → **1436.7 req/s** handled; 14136 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 6090.5 | 13573.1 | 18733.7 | 19260.2 |
| service time (from actual send) | 1107.4 | 4186.5 | 9251.6 | 10693.9 |
| client send lag | 4780.3 | 9836.9 | 10628.6 | 11081.7 |
| ↳ seller: waiting for a DB connection | 0.0 | 909.8 | 991.0 | 1001.7 |
| ↳ seller: allocator queries | 3.8 | 12.2 | 68.8 | 242.7 |
| ↳ seller: whole handler | 1008.4 | 1130.5 | 1246.7 | 1518.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 61.8 | 4141.0 | 9236.5 | 10469.0 |

Responses by HTTP status: `{'0': 14136, '200': 100, '409': 19597, '503': 26167}`  
Requests by kind: `{'fresh': 60000}`  
Transport errors: `{'TimeoutError': 12530, 'ClientOSError': 1606}`  
First sold-out answer at t = 0.161 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2, 'sold_out_fast': 24969, 'sold_out_checks': 2}`  
Client health: 4 worker processes, CPU per worker `['29%', '28%', '26%', '25%']` of one core; send lag p99 10628.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
