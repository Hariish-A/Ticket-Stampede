# Run `sweep-2000`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 10000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T09:12:51+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 6907 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 425 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 10000 responses in 9.066 s → **1103.0 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1022.8 | 4381.0 | 4522.0 | 4834.1 |
| service time (from actual send) | 1021.6 | 4380.1 | 4521.3 | 4833.6 |
| client send lag | 0.7 | 1.2 | 15.9 | 39.5 |
| ↳ seller: waiting for a DB connection | 0.0 | 945.6 | 998.3 | 1001.7 |
| ↳ seller: allocator queries | 10.2 | 24.3 | 69.1 | 171.7 |
| ↳ seller: whole handler | 74.1 | 1010.2 | 1059.0 | 1202.3 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 17.5 | 4359.3 | 4500.6 | 4527.9 |

Responses by HTTP status: `{'200': 100, '409': 6897, '503': 3003}`  
Requests by kind: `{'fresh': 10000}`  
First sold-out answer at t = 0.168 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 6907, 'sold_out_checks': 6907}`  
Client health: 4 worker processes, CPU per worker `['24%', '24%', '24%', '23%']` of one core; send lag p99 15.9 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
