# Run `c1-skiplocked`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:43:30+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 13 rejected (422), 0 refused otherwise (e.g. 409), 7 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 49861 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1165 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 62 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 476 snapshots over 52.0s, 0 violations |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.63 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.6 | 32.0 | 674.9 | 1188.7 |
| service time (from actual send) | 1.8 | 31.2 | 658.8 | 1185.6 |
| client send lag | 0.7 | 1.1 | 13.9 | 79.8 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 37.1 | 434.0 |
| ↳ seller: allocator queries | 0.4 | 3.5 | 11.3 | 350.9 |
| ↳ seller: whole handler | 0.9 | 16.4 | 63.9 | 443.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.9 | 6.4 | 665.1 | 1181.0 |

Responses by HTTP status: `{'200': 102, '409': 49856, '503': 1042}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.56 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 10, 'sold_out_checks': 10, 'sold_out_fast': 49851, 'admission_shed': 1068}`  
Client health: 4 worker processes, CPU per worker `['17%', '16%', '16%', '16%']` of one core; send lag p99 13.9 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 48888, 'turned_away_known': 1012, 'purchased': 100}`. 1028 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 1042, 'purchased': 102, 'sold_out': 49856}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 102 | 1119 | 0 | 822 | 0 | 169.7 | 1181.8 |
| 1 | 1017 | 0 | 0 | 1009 | 0 | 8 | 0 | 9.1 | 103.7 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 2.3 | 16.9 |
| 3 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 3.8 |
| 4 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.4 | 43.6 |
| 5 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.1 | 6.4 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.7 | 23.6 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.2 | 26.2 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 2.9 | 36.8 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.3 | 16.4 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.7 | 22.3 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.9 | 34.6 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.9 | 3.2 |
| 13 | 1027 | 0 | 0 | 1004 | 0 | 23 | 0 | 2.4 | 91.7 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.4 | 35.7 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.1 | 18.6 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.6 | 15.4 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.9 | 30.2 |
| 18 | 1023 | 0 | 0 | 1017 | 0 | 6 | 0 | 3.8 | 95.2 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.3 | 64.3 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 3.1 | 42.1 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.9 | 31.0 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 2.2 | 4.8 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.0 | 60.2 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.9 | 16.5 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 4.8 | 65.3 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.0 | 32.9 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 29.1 | 69.2 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 3.1 | 51.7 |
| 29 | 1017 | 0 | 0 | 959 | 0 | 58 | 0 | 2.6 | 120.9 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 2.6 | 25.9 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 10.3 | 64.1 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.5 | 68.9 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.3 | 26.0 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.6 | 22.0 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.4 | 8.5 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.1 | 60.4 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.1 | 7.7 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.3 | 33.0 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.0 | 61.9 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 2.5 | 15.8 |
| 41 | 1023 | 0 | 0 | 967 | 0 | 56 | 0 | 14.9 | 148.6 |
| 42 | 1016 | 0 | 0 | 990 | 0 | 26 | 0 | 2.4 | 93.1 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.1 | 15.6 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.8 | 67.7 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.1 | 3.7 |
| 46 | 1026 | 0 | 0 | 997 | 0 | 29 | 0 | 2.6 | 96.2 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.4 | 40.7 |
| 48 | 1017 | 0 | 0 | 1003 | 0 | 14 | 0 | 2.2 | 105.3 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 10.7 | 14.4 |
