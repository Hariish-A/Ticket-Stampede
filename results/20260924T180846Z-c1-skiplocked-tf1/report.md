# Run `c1-skiplocked-tf1`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T18:08:46+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 50908 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1050 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 62 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 494 snapshots over 52.1s, 0 violations |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 51000 responses in 49.632 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.0 | 5.8 | 1103.0 | 1239.4 |
| service time (from actual send) | 2.3 | 4.8 | 1066.6 | 1236.1 |
| client send lag | 0.7 | 1.2 | 13.5 | 138.6 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 0.1 | 343.4 |
| ↳ seller: allocator queries | 0.5 | 1.0 | 4.5 | 232.3 |
| ↳ seller: whole handler | 0.9 | 2.4 | 14.6 | 468.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.3 | 2.5 | 1054.7 | 1230.1 |

Responses by HTTP status: `{'200': 102, '409': 50898}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 0.632 s  
Seller counters during the run (GET /metrics): `{'claims': 40, 'blocking_fallbacks': 6, 'sold_out_fast': 16927, 'sold_out_checks': 6}`  
Client health: 4 worker processes, CPU per worker `['21%', '20%', '21%', '20%']` of one core; send lag p99 13.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 49900, 'purchased': 100}`. 0 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'purchased': 102, 'sold_out': 50898}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 102 | 1941 | 0 | 0 | 0 | 928.2 | 1227.8 |
| 1 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 3.2 | 64.8 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 2.5 | 4.1 |
| 3 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.6 | 4.8 |
| 4 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.4 | 3.7 |
| 5 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.5 | 4.5 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.7 | 5.6 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.8 | 4.6 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 2.8 | 7.4 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.4 | 3.8 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.2 | 10.1 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.5 | 4.6 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.6 | 6.2 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.9 | 6.6 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.6 | 4.8 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 3.5 | 9.0 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.8 | 5.6 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 3.0 | 10.5 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 4.3 | 19.3 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 3.1 | 6.0 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 3.2 | 5.9 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.1 | 6.3 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 3.1 | 5.9 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.5 | 7.6 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 2.8 | 5.0 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.3 | 6.7 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.7 | 4.5 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 3.8 | 12.9 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 3.8 | 28.3 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.9 | 5.1 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 3.7 | 6.9 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.9 | 5.4 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.5 | 9.9 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.8 | 6.1 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 3.2 | 5.7 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 3.0 | 16.7 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.6 | 4.3 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 3.6 | 15.2 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.6 | 10.8 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.8 | 4.8 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 3.4 | 7.4 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.3 | 5.8 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 3.0 | 24.0 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 4.0 | 17.7 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.0 | 6.1 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.0 | 5.7 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.4 | 4.5 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 3.2 | 11.9 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 3.7 | 11.5 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 13.3 | 15.7 |
