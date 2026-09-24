# Run `sweep-tf1-2000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 2000.0/s) · seed 1 · 2026-09-24T18:10:38+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 29908 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1053 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 30000 responses in 15.028 s → **1996.3 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 7.0 | 160.4 | 629.5 | 1068.1 |
| service time (from actual send) | 6.2 | 159.1 | 627.8 | 1066.7 |
| client send lag | 0.8 | 1.3 | 3.6 | 23.9 |
| ↳ seller: waiting for a DB connection | 0.1 | 63.4 | 348.6 | 996.7 |
| ↳ seller: allocator queries | 1.3 | 11.2 | 26.3 | 288.9 |
| ↳ seller: whole handler | 3.7 | 105.5 | 385.5 | 1031.4 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 2.6 | 19.2 | 546.4 | 675.9 |

Responses by HTTP status: `{'200': 100, '409': 29898, '502': 2}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'JSONDecodeError': 2}`  
First sold-out answer at t = 0.29 s  
Seller counters during the run (GET /metrics): `{'claims': 40, 'sold_out_fast': 9961, 'blocking_fallbacks': -1, 'sold_out_checks': -1}`  
Client health: 8 worker processes, CPU per worker `['27%', '26%', '26%', '26%', '26%', '26%', '26%', '27%']` of one core; send lag p99 3.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

30000 buyers (user, request_id): final answers `{'purchased': 100, 'sold_out': 29898, 'still_unknown': 2}`. 2 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 2, 'purchased': 100, 'sold_out': 29898}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1999 | 0 | 100 | 1899 | 0 | 0 | 0 | 63.1 | 682.1 |
| 1 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 6.4 | 19.8 |
| 2 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 3.3 | 7.2 |
| 3 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 3.4 | 8.6 |
| 4 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 4.3 | 22.5 |
| 5 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 3.3 | 8.0 |
| 6 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 55.5 | 268.4 |
| 7 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 8.2 | 137.0 |
| 8 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 4.1 | 16.5 |
| 9 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 15.6 | 220.7 |
| 10 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 5.5 | 158.4 |
| 11 | 2000 | 0 | 0 | 1998 | 0 | 0 | 0 | 11.6 | 432.2 |
| 12 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 40.1 | 308.8 |
| 13 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 95.4 | 801.1 |
| 14 | 2000 | 0 | 0 | 2000 | 0 | 0 | 0 | 86.8 | 505.2 |
| 15 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 28.6 | 28.6 |
