# Run `sweep-4000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 60000 requests (burst 0 at t=0, then 4000.0/s) · seed 1 · 2026-09-24T09:28:17+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 21265 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 543 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 46903 responses in 33.194 s → **1413.0 req/s** handled; 13097 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 6495.8 | 15378.2 | 19555.9 | 20269.0 |
| service time (from actual send) | 1096.1 | 5746.5 | 9836.2 | 10514.0 |
| client send lag | 4905.9 | 9974.7 | 11001.4 | 11289.9 |
| ↳ seller: waiting for a DB connection | 0.0 | 924.3 | 994.3 | 1003.6 |
| ↳ seller: allocator queries | 3.6 | 11.9 | 76.7 | 321.1 |
| ↳ seller: whole handler | 1005.8 | 1116.9 | 1200.5 | 1574.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 63.8 | 5734.6 | 9826.1 | 10454.1 |

Responses by HTTP status: `{'0': 13097, '200': 100, '409': 21255, '503': 25548}`  
Requests by kind: `{'fresh': 60000}`  
Transport errors: `{'TimeoutError': 12871, 'ClientOSError': 226}`  
First sold-out answer at t = 0.131 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 4, 'sold_out_checks': 4, 'sold_out_fast': 27204}`  
Client health: 4 worker processes, CPU per worker `['25%', '27%', '28%', '26%']` of one core; send lag p99 11001.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
