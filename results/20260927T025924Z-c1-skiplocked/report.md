# Run `c1-skiplocked`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:59:24+00:00

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
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 2 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 62 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 495 snapshots over 52.1s, 0 violations |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.634 s → **1027.5 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.0 | 3.5 | 665.6 | 1089.9 |
| service time (from actual send) | 1.3 | 2.7 | 656.2 | 1086.7 |
| client send lag | 0.7 | 1.1 | 12.4 | 72.2 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 17.4 | 441.7 |
| ↳ seller: allocator queries | 0.3 | 0.6 | 6.2 | 182.7 |
| ↳ seller: whole handler | 0.6 | 1.3 | 39.4 | 450.9 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 1.1 | 663.2 | 1082.2 |

Responses by HTTP status: `{'200': 102, '409': 49856, '503': 1042}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.565 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 9, 'sold_out_checks': 9, 'sold_out_fast': 49852, 'admission_shed': 1068}`  
Client health: 4 worker processes, CPU per worker `['13%', '13%', '13%', '13%']` of one core; send lag p99 12.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 48891, 'turned_away_known': 1009, 'purchased': 100}`. 1030 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 1042, 'purchased': 102, 'sold_out': 49856}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 102 | 1083 | 0 | 858 | 0 | 174.3 | 1081.7 |
| 1 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.2 | 41.5 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 2.0 | 3.7 |
| 3 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 3.5 |
| 4 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.2 | 4.3 |
| 5 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.0 | 3.9 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 3.5 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.1 | 3.8 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 2.3 | 23.8 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 1.9 | 3.5 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.0 | 4.0 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.0 | 21.6 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.1 | 4.6 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.0 | 3.6 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 3.7 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.0 | 23.7 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 3.5 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 1.9 | 3.7 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.2 | 7.0 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.0 | 3.7 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 1.9 | 3.9 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.0 | 6.4 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 1.9 | 3.7 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 1.9 | 3.7 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 1.8 | 3.2 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.8 | 4.1 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.8 | 3.1 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 1.9 | 3.4 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.4 | 21.7 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 1.8 | 33.8 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 1.9 | 4.0 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 3.9 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.2 | 44.2 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 1.9 | 3.6 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.1 | 4.6 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 1.9 | 3.8 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.8 | 3.3 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.0 | 3.7 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.2 | 6.5 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 3.5 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 1.8 | 3.7 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 4.4 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.0 | 3.6 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 1.8 | 3.2 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 1.8 | 3.2 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.8 | 3.1 |
| 46 | 1026 | 0 | 0 | 955 | 0 | 71 | 0 | 5.3 | 132.9 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.1 | 4.0 |
| 48 | 1017 | 0 | 0 | 904 | 0 | 113 | 0 | 27.4 | 141.3 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 10.9 | 17.8 |
