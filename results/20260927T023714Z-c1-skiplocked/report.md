# Run `c1-skiplocked`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:37:14+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 49965 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1160 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 62 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 463 snapshots over 52.1s, 0 violations |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.634 s → **1027.5 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.8 | 53.4 | 923.0 | 1712.2 |
| service time (from actual send) | 2.0 | 52.6 | 902.3 | 1711.1 |
| client send lag | 0.7 | 1.2 | 29.7 | 139.6 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 176.8 | 933.7 |
| ↳ seller: allocator queries | 0.4 | 4.4 | 13.3 | 422.9 |
| ↳ seller: whole handler | 1.0 | 27.7 | 199.8 | 945.7 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.9 | 7.9 | 776.5 | 1687.0 |

Responses by HTTP status: `{'200': 102, '409': 49955, '503': 943}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.779 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 11, 'sold_out_fast': 49954, 'sold_out_checks': 11, 'admission_shed': 943}`  
Client health: 4 worker processes, CPU per worker `['17%', '17%', '17%', '17%']` of one core; send lag p99 29.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 48984, 'turned_away_known': 916, 'purchased': 100}`. 931 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 943, 'purchased': 102, 'sold_out': 49955}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 102 | 998 | 0 | 943 | 0 | 336.5 | 1644.9 |
| 1 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 21.2 | 127.8 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 3.6 | 101.1 |
| 3 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.8 | 7.5 |
| 4 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 4.1 | 65.9 |
| 5 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 4.0 | 35.9 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 5.4 | 88.1 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 5.0 | 109.0 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 3.1 | 108.0 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.9 | 31.3 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.2 | 67.1 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 14.6 | 180.3 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.5 | 25.4 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.4 | 103.1 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.9 | 32.4 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.1 | 3.9 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.0 | 17.6 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 8.5 | 174.0 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.0 | 35.7 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.4 | 5.4 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.5 | 7.1 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.9 | 6.5 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 2.7 | 6.6 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.1 | 63.6 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 3.1 | 56.0 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.5 | 44.1 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 3.2 | 139.0 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 31.6 | 190.8 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 52.4 | 261.8 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.2 | 23.5 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 2.2 | 25.2 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.1 | 4.0 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.3 | 23.6 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.3 | 7.8 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.2 | 4.3 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.5 | 55.5 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 4.3 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 97.4 | 473.0 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.6 | 226.2 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 3.8 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 2.2 | 51.1 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 34.8 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.4 | 30.4 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.3 | 4.5 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.5 | 34.5 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.0 | 3.8 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.2 | 147.2 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.2 | 8.8 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 7.4 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 11.2 | 18.9 |
