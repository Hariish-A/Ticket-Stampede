# Run `slowdb-closed`

target `http://seller1:8000` · allocator **skiplocked** · closed-loop x4, 4 processes · 15000 tickets · 41016 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T10:13:52+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 15000 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1066 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 25646 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 755 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 440 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 410 snapshots over 80.6s, 0 violations (7 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 41016 responses in 78.152 s → **524.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.1 | 9.1 | 73.5 | 3005.5 |
| service time (from actual send) | 3.1 | 9.1 | 73.5 | 3005.5 |
| client send lag | 0.0 | 0.0 | 0.0 | 0.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 0.1 | 32.9 |
| ↳ seller: allocator queries | 1.4 | 7.1 | 32.4 | 122.6 |
| ↳ seller: whole handler | 2.2 | 8.0 | 64.8 | 3004.1 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.8 | 1.2 | 30.8 | 90.6 |

Responses by HTTP status: `{'200': 15364, '409': 25636, '503': 16}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 16}`  
First sold-out answer at t = 49.966 s  
Seller counters during the run (GET /metrics): `{'claims': 14996, 'unique_violation_retries': 5, 'blocking_fallbacks': 1, 'sold_out_checks': 1, 'sold_out_fast': 25645}`  
Client health: 4 worker processes, CPU per worker `['5%', '5%', '5%', '5%']` of one core; send lag p99 0.0 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 15000, 'sold_out': 25000}`. 4 got at least one unclear answer (503 or no response); **4 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 12, 'purchased': 15364, 'sold_out': 25636, 'unknown': 4}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 558 | 0 | 558 | 0 | 0 | 0 | 0 | 5.9 | 36.9 |
| 1 | 575 | 0 | 575 | 0 | 0 | 0 | 0 | 6.2 | 15.8 |
| 2 | 584 | 0 | 584 | 0 | 0 | 0 | 0 | 6.1 | 14.5 |
| 3 | 395 | 0 | 395 | 0 | 0 | 0 | 0 | 9.8 | 18.8 |
| 4 | 367 | 0 | 363 | 0 | 4 | 0 | 0 | 10.1 | 3003.7 |
| 8 ⚡ | 4 | 4 | 0 | 0 | 0 | 4 | 0 | 1001.3 | 1001.6 |
| 10 ⚡ | 4 | 4 | 0 | 0 | 0 | 4 | 0 | 1001.6 | 1003.2 |
| 12 ⚡ | 4 | 4 | 0 | 0 | 0 | 4 | 0 | 1002.0 | 1003.0 |
| 16 | 136 | 2 | 136 | 0 | 0 | 0 | 0 | 5.4 | 41.7 |
| 17 | 373 | 2 | 373 | 0 | 0 | 0 | 0 | 5.8 | 23.8 |
| 18 | 528 | 0 | 528 | 0 | 0 | 0 | 0 | 6.3 | 22.5 |
| 19 | 501 | 0 | 501 | 0 | 0 | 0 | 0 | 6.5 | 24.6 |
| 20 | 509 | 0 | 509 | 0 | 0 | 0 | 0 | 6.2 | 30.9 |
| 21 | 485 | 0 | 485 | 0 | 0 | 0 | 0 | 6.8 | 28.7 |
| 22 | 417 | 0 | 417 | 0 | 0 | 0 | 0 | 8.0 | 51.6 |
| 23 | 420 | 0 | 420 | 0 | 0 | 0 | 0 | 7.9 | 43.2 |
| 24 | 431 | 0 | 431 | 0 | 0 | 0 | 0 | 7.1 | 43.8 |
| 25 | 410 | 0 | 410 | 0 | 0 | 0 | 0 | 6.9 | 59.8 |
| 26 | 446 | 0 | 446 | 0 | 0 | 0 | 0 | 6.3 | 40.3 |
| 27 | 455 | 0 | 455 | 0 | 0 | 0 | 0 | 6.5 | 44.2 |
| 28 | 416 | 0 | 416 | 0 | 0 | 0 | 0 | 6.7 | 44.5 |
| 29 | 461 | 0 | 461 | 0 | 0 | 0 | 0 | 6.2 | 45.3 |
| 30 | 391 | 0 | 391 | 0 | 0 | 0 | 0 | 6.9 | 66.8 |
| 31 | 403 | 0 | 403 | 0 | 0 | 0 | 0 | 6.4 | 64.9 |
| 32 | 375 | 0 | 375 | 0 | 0 | 0 | 0 | 6.7 | 81.7 |
| 33 | 408 | 0 | 408 | 0 | 0 | 0 | 0 | 6.4 | 52.8 |
| 34 | 352 | 0 | 352 | 0 | 0 | 0 | 0 | 8.1 | 98.2 |
| 35 | 351 | 0 | 351 | 0 | 0 | 0 | 0 | 6.7 | 71.7 |
| 36 | 416 | 0 | 416 | 0 | 0 | 0 | 0 | 6.3 | 61.2 |
| 37 | 337 | 0 | 337 | 0 | 0 | 0 | 0 | 7.5 | 78.4 |
| 38 | 406 | 0 | 406 | 0 | 0 | 0 | 0 | 6.3 | 65.2 |
| 39 | 306 | 0 | 306 | 0 | 0 | 0 | 0 | 6.6 | 98.0 |
| 40 | 320 | 0 | 320 | 0 | 0 | 0 | 0 | 6.7 | 107.2 |
| 41 | 319 | 0 | 319 | 0 | 0 | 0 | 0 | 6.6 | 93.7 |
| 42 | 337 | 0 | 337 | 0 | 0 | 0 | 0 | 6.8 | 83.1 |
| 43 | 332 | 0 | 332 | 0 | 0 | 0 | 0 | 6.5 | 87.3 |
| 44 | 297 | 0 | 297 | 0 | 0 | 0 | 0 | 7.9 | 96.1 |
| 45 | 313 | 0 | 313 | 0 | 0 | 0 | 0 | 7.7 | 88.5 |
| 46 | 319 | 0 | 319 | 0 | 0 | 0 | 0 | 7.0 | 90.0 |
| 47 | 318 | 0 | 318 | 0 | 0 | 0 | 0 | 6.8 | 92.3 |
| 48 | 303 | 0 | 303 | 0 | 0 | 0 | 0 | 7.8 | 87.4 |
| 49 | 342 | 0 | 291 | 51 | 0 | 0 | 0 | 6.2 | 92.9 |
| 50 | 942 | 0 | 5 | 937 | 0 | 0 | 0 | 2.6 | 77.2 |
| 51 | 954 | 0 | 2 | 952 | 0 | 0 | 0 | 2.5 | 66.9 |
| 52 | 739 | 0 | 0 | 739 | 0 | 0 | 0 | 3.1 | 88.5 |
| 53 | 873 | 0 | 0 | 873 | 0 | 0 | 0 | 2.7 | 69.6 |
| 54 | 825 | 0 | 0 | 825 | 0 | 0 | 0 | 2.7 | 74.6 |
| 55 | 808 | 0 | 0 | 808 | 0 | 0 | 0 | 2.8 | 77.2 |
| 56 | 936 | 0 | 0 | 936 | 0 | 0 | 0 | 2.5 | 70.5 |
| 57 | 887 | 0 | 0 | 887 | 0 | 0 | 0 | 2.8 | 72.6 |
| 58 | 930 | 0 | 0 | 930 | 0 | 0 | 0 | 2.6 | 67.9 |
| 59 | 907 | 0 | 0 | 907 | 0 | 0 | 0 | 2.6 | 68.9 |
| 60 | 970 | 0 | 0 | 970 | 0 | 0 | 0 | 2.5 | 75.1 |
| 61 | 904 | 0 | 0 | 904 | 0 | 0 | 0 | 2.6 | 73.9 |
| 62 | 893 | 0 | 0 | 893 | 0 | 0 | 0 | 2.6 | 72.1 |
| 63 | 997 | 0 | 0 | 997 | 0 | 0 | 0 | 2.5 | 67.0 |
| 64 | 758 | 0 | 0 | 758 | 0 | 0 | 0 | 2.9 | 78.8 |
| 65 | 860 | 0 | 0 | 860 | 0 | 0 | 0 | 2.9 | 76.9 |
| 66 | 856 | 0 | 0 | 856 | 0 | 0 | 0 | 2.7 | 72.5 |
| 67 | 949 | 0 | 0 | 949 | 0 | 0 | 0 | 2.6 | 69.7 |
| 68 | 912 | 0 | 0 | 912 | 0 | 0 | 0 | 2.6 | 68.9 |
| 69 | 947 | 0 | 0 | 947 | 0 | 0 | 0 | 2.5 | 71.3 |
| 70 | 1093 | 0 | 0 | 1093 | 0 | 0 | 0 | 2.4 | 72.6 |
| 71 | 942 | 0 | 0 | 942 | 0 | 0 | 0 | 2.5 | 70.8 |
| 72 | 961 | 0 | 0 | 961 | 0 | 0 | 0 | 2.4 | 68.1 |
| 73 | 1070 | 0 | 0 | 1070 | 0 | 0 | 0 | 2.5 | 72.5 |
| 74 | 871 | 0 | 0 | 871 | 0 | 0 | 0 | 2.5 | 79.8 |
| 75 | 958 | 0 | 0 | 958 | 0 | 0 | 0 | 2.6 | 74.7 |
| 76 | 1008 | 0 | 0 | 1008 | 0 | 0 | 0 | 2.4 | 66.4 |
| 77 | 801 | 0 | 0 | 801 | 0 | 0 | 0 | 2.3 | 65.2 |
| 78 | 41 | 0 | 0 | 41 | 0 | 0 | 0 | 1.8 | 77.4 |

⚡ = fault active (t=5.0–15.0 s)
