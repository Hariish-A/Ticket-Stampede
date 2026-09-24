# Run `c2-brief-serializable`

target `http://seller1:8000` · allocator **serializable** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T08:46:55+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 48639 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 328 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 62 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 432 snapshots over 52.0s, 0 violations (1 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.631 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.8 | 295.4 | 1890.6 | 2919.1 |
| service time (from actual send) | 3.1 | 294.7 | 1876.9 | 2918.7 |
| client send lag | 0.7 | 1.1 | 11.9 | 87.5 |

Responses by HTTP status: `{'200': 100, '409': 48629, '503': 2271}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 1.793 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'serialization_retries': 1785, 'serialization_gave_up': 11, 'sold_out_checks': 48639}`  
Client health: 4 worker processes, CPU per worker `['12%', '12%', '12%', '12%']` of one core; send lag p99 11.9 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
