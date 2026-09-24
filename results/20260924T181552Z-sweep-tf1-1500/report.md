# Run `sweep-tf1-1500`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 1500.0/s) · seed 1 · 2026-09-24T18:15:52+00:00

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
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1062 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 30000 responses in 20.006 s → **1499.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.6 | 6.3 | 122.2 | 347.5 |
| service time (from actual send) | 2.8 | 5.5 | 121.5 | 347.0 |
| client send lag | 0.8 | 1.2 | 1.5 | 17.8 |
| ↳ seller: waiting for a DB connection | 0.1 | 0.1 | 6.1 | 254.5 |
| ↳ seller: allocator queries | 0.6 | 1.2 | 7.9 | 179.0 |
| ↳ seller: whole handler | 1.2 | 3.0 | 63.6 | 283.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.6 | 2.5 | 28.4 | 263.5 |

Responses by HTTP status: `{'200': 100, '409': 29898, '502': 2}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'JSONDecodeError': 2}`  
First sold-out answer at t = 0.227 s  
Seller counters during the run (GET /metrics): `{'claims': 32, 'sold_out_fast': 10284, 'blocking_fallbacks': 10, 'sold_out_checks': 10}`  
Client health: 8 worker processes, CPU per worker `['18%', '18%', '18%', '18%', '18%', '18%', '18%', '18%']` of one core; send lag p99 1.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

30000 buyers (user, request_id): final answers `{'purchased': 100, 'sold_out': 29898, 'still_unknown': 2}`. 2 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 2, 'purchased': 100, 'sold_out': 29898}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1499 | 0 | 100 | 1397 | 0 | 0 | 0 | 4.8 | 293.0 |
| 1 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.7 | 48.0 |
| 2 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.9 | 12.1 |
| 3 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.4 | 15.4 |
| 4 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.7 | 10.2 |
| 5 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.0 | 15.4 |
| 6 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.0 | 9.7 |
| 7 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 7.0 |
| 8 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.9 | 5.4 |
| 9 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.0 | 10.0 |
| 10 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.5 | 14.5 |
| 11 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 6.7 |
| 12 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.6 | 86.2 |
| 13 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 12.9 |
| 14 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.7 | 13.3 |
| 15 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.6 | 9.5 |
| 16 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.2 | 5.9 |
| 17 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.2 | 6.8 |
| 18 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 7.7 |
| 19 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.8 | 9.5 |
| 20 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 8.1 | 8.1 |
