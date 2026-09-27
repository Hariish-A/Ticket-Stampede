# Run `c1-skiplocked`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:41:24+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 50870 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1163 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 61 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 474 snapshots over 52.1s, 0 violations |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.629 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.6 | 30.8 | 1846.3 | 2067.4 |
| service time (from actual send) | 1.8 | 30.0 | 1826.5 | 2067.2 |
| client send lag | 0.7 | 1.1 | 14.1 | 120.9 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 383.6 | 947.9 |
| ↳ seller: allocator queries | 0.4 | 3.5 | 10.4 | 232.7 |
| ↳ seller: whole handler | 0.9 | 16.9 | 422.4 | 1005.4 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.9 | 6.2 | 1820.1 | 2054.0 |

Responses by HTTP status: `{'200': 101, '409': 50860, '503': 39}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.663 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 18, 'sold_out_checks': 18, 'sold_out_fast': 50852}`  
Client health: 4 worker processes, CPU per worker `['16%', '16%', '16%', '16%']` of one core; send lag p99 14.1 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 49862, 'purchased': 100, 'turned_away_known': 38}`. 39 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 39, 'purchased': 101, 'sold_out': 50860}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 101 | 1903 | 0 | 39 | 0 | 1118.4 | 2052.7 |
| 1 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 24.0 | 398.9 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 10.9 | 61.6 |
| 3 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.3 | 4.5 |
| 4 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 3.9 | 48.9 |
| 5 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.7 | 47.3 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.6 | 6.3 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 3.5 | 43.8 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 10.4 | 140.2 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.6 | 45.9 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 4.8 | 34.9 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.4 | 27.7 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.9 | 24.5 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.9 | 56.2 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.4 | 5.4 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.3 | 115.2 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.0 | 20.8 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.5 | 19.4 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 29.8 | 196.1 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 3.1 | 173.6 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.2 | 28.8 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.4 | 47.0 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 3.2 | 31.1 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.8 | 35.4 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 3.1 | 21.8 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.2 | 6.1 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.8 | 3.5 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 2.0 | 4.0 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.5 | 55.2 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 1.9 | 4.0 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 2.0 | 5.1 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 5.9 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.1 | 5.6 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.0 | 3.6 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.3 | 129.8 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.6 | 96.7 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.0 | 11.2 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.2 | 21.8 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.5 | 45.1 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 4.2 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 2.1 | 34.4 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.1 | 182.0 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.9 | 154.9 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 4.8 | 27.2 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.6 | 74.0 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.7 | 39.5 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.2 | 36.8 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.3 | 43.6 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.3 | 66.3 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 11.8 | 53.0 |
