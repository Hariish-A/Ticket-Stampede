# Run `slowdb-closed`

target `http://seller1:8000` · allocator **skiplocked** · closed-loop x4, 4 processes · 15000 tickets · 41016 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T10:33:37+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 15000 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1066 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 25642 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 762 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 444 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 379 snapshots over 74.0s, 0 violations (7 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 41016 responses in 71.153 s → **576.5 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.8 | 8.8 | 65.3 | 3004.6 |
| service time (from actual send) | 2.8 | 8.8 | 65.3 | 3004.6 |
| client send lag | 0.0 | 0.0 | 0.0 | 0.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 0.1 | 38.1 |
| ↳ seller: allocator queries | 1.0 | 6.8 | 28.5 | 123.7 |
| ↳ seller: whole handler | 1.9 | 7.7 | 60.3 | 3003.4 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.8 | 1.2 | 7.8 | 89.7 |

Responses by HTTP status: `{'200': 15368, '409': 25632, '503': 16}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 16}`  
First sold-out answer at t = 46.691 s  
Seller counters during the run (GET /metrics): `{'claims': 14997, 'unique_violation_retries': 2, 'blocking_fallbacks': 3, 'sold_out_fast': 25639, 'sold_out_checks': 3}`  
Client health: 4 worker processes, CPU per worker `['6%', '6%', '6%', '6%']` of one core; send lag p99 0.0 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 15000, 'sold_out': 25000}`. 4 got at least one unclear answer (503 or no response); **3 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 1 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 13, 'purchased': 15368, 'sold_out': 25632, 'unknown': 3}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 578 | 0 | 578 | 0 | 0 | 0 | 0 | 6.2 | 14.2 |
| 1 | 560 | 0 | 560 | 0 | 0 | 0 | 0 | 6.5 | 18.1 |
| 2 | 568 | 0 | 568 | 0 | 0 | 0 | 0 | 6.3 | 16.4 |
| 3 | 577 | 0 | 577 | 0 | 0 | 0 | 0 | 6.0 | 16.9 |
| 4 | 546 | 0 | 543 | 0 | 3 | 0 | 0 | 6.4 | 34.3 |
| 6 ⚡ | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1001.5 | 1001.5 |
| 7 ⚡ | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 1001.6 | 1001.6 |
| 8 ⚡ | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 1001.2 | 1003.0 |
| 9 ⚡ | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 1002.3 | 1002.3 |
| 10 ⚡ | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 1001.8 | 1002.2 |
| 11 ⚡ | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 1001.6 | 1001.6 |
| 12 ⚡ | 3 | 3 | 0 | 0 | 0 | 3 | 0 | 1002.4 | 1003.0 |
| 15 ⚡ | 125 | 1 | 125 | 0 | 0 | 0 | 0 | 5.5 | 30.6 |
| 16 | 174 | 1 | 174 | 0 | 0 | 0 | 0 | 5.3 | 21.6 |
| 17 | 401 | 2 | 401 | 0 | 0 | 0 | 0 | 5.6 | 23.4 |
| 18 | 514 | 0 | 514 | 0 | 0 | 0 | 0 | 6.3 | 23.1 |
| 19 | 517 | 0 | 517 | 0 | 0 | 0 | 0 | 6.1 | 25.2 |
| 20 | 486 | 0 | 486 | 0 | 0 | 0 | 0 | 6.7 | 29.2 |
| 21 | 459 | 0 | 459 | 0 | 0 | 0 | 0 | 7.1 | 37.4 |
| 22 | 499 | 0 | 499 | 0 | 0 | 0 | 0 | 6.2 | 33.8 |
| 23 | 469 | 0 | 469 | 0 | 0 | 0 | 0 | 6.5 | 35.1 |
| 24 | 470 | 0 | 470 | 0 | 0 | 0 | 0 | 6.4 | 37.4 |
| 25 | 444 | 0 | 444 | 0 | 0 | 0 | 0 | 6.6 | 39.4 |
| 26 | 486 | 0 | 486 | 0 | 0 | 0 | 0 | 5.9 | 50.2 |
| 27 | 425 | 0 | 425 | 0 | 0 | 0 | 0 | 6.6 | 43.5 |
| 28 | 461 | 0 | 461 | 0 | 0 | 0 | 0 | 6.2 | 41.7 |
| 29 | 430 | 0 | 430 | 0 | 0 | 0 | 0 | 6.9 | 48.7 |
| 30 | 425 | 0 | 425 | 0 | 0 | 0 | 0 | 6.5 | 60.4 |
| 31 | 367 | 0 | 367 | 0 | 0 | 0 | 0 | 8.6 | 75.4 |
| 32 | 419 | 0 | 419 | 0 | 0 | 0 | 0 | 6.5 | 53.2 |
| 33 | 405 | 0 | 405 | 0 | 0 | 0 | 0 | 6.3 | 59.3 |
| 34 | 384 | 0 | 384 | 0 | 0 | 0 | 0 | 7.8 | 71.0 |
| 35 | 408 | 0 | 408 | 0 | 0 | 0 | 0 | 6.6 | 55.1 |
| 36 | 336 | 0 | 336 | 0 | 0 | 0 | 0 | 7.8 | 75.3 |
| 37 | 404 | 0 | 404 | 0 | 0 | 0 | 0 | 6.5 | 60.0 |
| 38 | 343 | 0 | 343 | 0 | 0 | 0 | 0 | 8.0 | 98.9 |
| 39 | 353 | 0 | 353 | 0 | 0 | 0 | 0 | 6.8 | 72.8 |
| 40 | 379 | 0 | 379 | 0 | 0 | 0 | 0 | 6.7 | 76.4 |
| 41 | 314 | 0 | 314 | 0 | 0 | 0 | 0 | 8.4 | 101.8 |
| 42 | 399 | 0 | 399 | 0 | 0 | 0 | 0 | 6.7 | 72.2 |
| 43 | 364 | 0 | 364 | 0 | 0 | 0 | 0 | 6.7 | 91.5 |
| 44 | 361 | 0 | 361 | 0 | 0 | 0 | 0 | 6.6 | 93.2 |
| 45 | 308 | 0 | 308 | 0 | 0 | 0 | 0 | 7.1 | 91.4 |
| 46 | 635 | 0 | 205 | 430 | 0 | 0 | 0 | 2.4 | 84.8 |
| 47 | 1113 | 0 | 8 | 1105 | 0 | 0 | 0 | 2.2 | 67.7 |
| 48 | 1078 | 0 | 0 | 1078 | 0 | 0 | 0 | 2.3 | 66.9 |
| 49 | 1120 | 0 | 0 | 1120 | 0 | 0 | 0 | 2.2 | 66.4 |
| 50 | 1035 | 0 | 0 | 1035 | 0 | 0 | 0 | 2.4 | 67.5 |
| 51 | 991 | 0 | 0 | 991 | 0 | 0 | 0 | 2.6 | 69.3 |
| 52 | 1036 | 0 | 0 | 1036 | 0 | 0 | 0 | 2.4 | 65.7 |
| 53 | 1122 | 0 | 0 | 1122 | 0 | 0 | 0 | 2.2 | 64.5 |
| 54 | 1074 | 0 | 0 | 1074 | 0 | 0 | 0 | 2.4 | 66.1 |
| 55 | 1098 | 0 | 0 | 1098 | 0 | 0 | 0 | 2.3 | 62.7 |
| 56 | 1085 | 0 | 0 | 1085 | 0 | 0 | 0 | 2.3 | 67.3 |
| 57 | 1048 | 0 | 0 | 1048 | 0 | 0 | 0 | 2.2 | 66.8 |
| 58 | 1129 | 0 | 0 | 1129 | 0 | 0 | 0 | 2.2 | 67.2 |
| 59 | 1113 | 0 | 0 | 1113 | 0 | 0 | 0 | 2.3 | 63.0 |
| 60 | 1041 | 0 | 0 | 1041 | 0 | 0 | 0 | 2.4 | 64.0 |
| 61 | 915 | 0 | 0 | 915 | 0 | 0 | 0 | 2.7 | 68.5 |
| 62 | 1136 | 0 | 0 | 1136 | 0 | 0 | 0 | 2.2 | 63.5 |
| 63 | 1107 | 0 | 0 | 1107 | 0 | 0 | 0 | 2.2 | 67.4 |
| 64 | 934 | 0 | 0 | 934 | 0 | 0 | 0 | 2.5 | 65.7 |
| 65 | 1093 | 0 | 0 | 1093 | 0 | 0 | 0 | 2.4 | 67.2 |
| 66 | 1095 | 0 | 0 | 1095 | 0 | 0 | 0 | 2.3 | 66.4 |
| 67 | 1098 | 0 | 0 | 1098 | 0 | 0 | 0 | 2.3 | 64.3 |
| 68 | 881 | 0 | 0 | 881 | 0 | 0 | 0 | 2.7 | 79.2 |
| 69 | 1073 | 0 | 0 | 1073 | 0 | 0 | 0 | 2.2 | 64.0 |
| 70 | 760 | 0 | 0 | 760 | 0 | 0 | 0 | 2.1 | 65.9 |
| 71 | 35 | 0 | 0 | 35 | 0 | 0 | 0 | 2.5 | 63.9 |

⚡ = fault active (t=5.0–15.0 s)
