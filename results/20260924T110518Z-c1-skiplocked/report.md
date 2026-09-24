# Run `c1-skiplocked`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T11:05:18+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 39072 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 858 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 64 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 290 snapshots over 52.2s, 0 violations (7 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 48653 responses in 49.652 s → **979.9 req/s** handled; 2347 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 21.0 | 1898.7 | 3465.2 | 10402.6 |
| service time (from actual send) | 20.2 | 1846.8 | 3463.9 | 10401.9 |
| client send lag | 0.8 | 1.4 | 339.6 | 763.7 |
| ↳ seller: waiting for a DB connection | 0.0 | 336.4 | 969.0 | 1002.5 |
| ↳ seller: allocator queries | 1.7 | 6.8 | 33.5 | 1587.9 |
| ↳ seller: whole handler | 13.3 | 1121.7 | 2356.6 | 5195.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 4.6 | 399.1 | 1913.2 | 10373.7 |

Responses by HTTP status: `{'0': 2347, '200': 103, '409': 39062, '503': 9488}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
Transport errors: `{'TimeoutError': 2347}`  
First sold-out answer at t = 0.835 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 7, 'sold_out_fast': 41398, 'sold_out_checks': 7}`  
Client health: 4 worker processes, CPU per worker `['25%', '26%', '24%', '26%']` of one core; send lag p99 339.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'sold_out': 38330, 'turned_away_known': 9254, 'purchased': 100, 'still_unknown': 2316}`. 11637 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 1 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'no_response': 2347, 'not_attempted': 9488, 'purchased': 103, 'sold_out': 39062}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 103 | 1594 | 0 | 346 | 0 | 1264.0 | 1946.3 |
| 1 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 168.0 | 836.6 |
| 2 | 1010 | 0 | 0 | 1010 | 0 | 0 | 0 | 9.4 | 54.6 |
| 3 | 1017 | 0 | 0 | 988 | 0 | 29 | 0 | 3.3 | 2717.2 |
| 4 | 1021 | 0 | 0 | 13 | 0 | 1008 | 0 | 2149.2 | 2646.5 |
| 5 | 1022 | 0 | 0 | 285 | 0 | 735 | 2 | 2487.6 | 9849.4 |
| 6 | 1020 | 0 | 0 | 97 | 0 | 322 | 601 | 2077.3 | 10381.4 |
| 7 | 1016 | 0 | 0 | 49 | 0 | 967 | 0 | 3191.9 | 4139.2 |
| 8 | 1011 | 0 | 0 | 1 | 0 | 600 | 410 | 3217.7 | 3488.6 |
| 9 | 1019 | 0 | 0 | 0 | 0 | 369 | 650 | 2622.4 | 2790.3 |
| 10 | 1027 | 0 | 0 | 15 | 0 | 457 | 555 | 2072.3 | 2546.4 |
| 11 | 1014 | 0 | 0 | 11 | 0 | 874 | 129 | 1371.2 | 1821.7 |
| 12 | 1021 | 0 | 0 | 98 | 0 | 923 | 0 | 1170.2 | 10310.7 |
| 13 | 1027 | 0 | 0 | 193 | 0 | 834 | 0 | 1091.2 | 1458.2 |
| 14 | 1017 | 0 | 0 | 353 | 0 | 664 | 0 | 1064.6 | 1276.9 |
| 15 | 1028 | 0 | 0 | 521 | 0 | 507 | 0 | 1024.2 | 1152.9 |
| 16 | 1023 | 0 | 0 | 683 | 0 | 340 | 0 | 884.9 | 1116.6 |
| 17 | 1016 | 0 | 0 | 666 | 0 | 350 | 0 | 726.8 | 1126.8 |
| 18 | 1023 | 0 | 0 | 866 | 0 | 157 | 0 | 522.1 | 1076.0 |
| 19 | 1025 | 0 | 0 | 1020 | 0 | 5 | 0 | 285.4 | 1003.4 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 17.3 | 274.8 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 14.7 | 182.0 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 12.2 | 36.0 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.4 | 23.7 |
| 24 | 1022 | 0 | 0 | 1021 | 0 | 1 | 0 | 186.5 | 880.6 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 40.6 | 469.1 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.8 | 25.4 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 2.7 | 73.6 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 152.8 | 575.2 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 4.1 | 129.8 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 22.9 | 108.2 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 7.4 | 57.0 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 3.1 | 138.5 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 3.3 | 33.3 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 5.1 | 97.8 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 8.9 | 74.8 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 8.1 | 42.3 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 9.7 | 95.5 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 224.1 | 734.3 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 18.5 | 273.8 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 4.3 | 112.6 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.7 | 23.0 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 3.8 | 18.1 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.0 | 36.7 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.6 | 12.7 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.7 | 26.2 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.6 | 25.3 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.6 | 90.0 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 9.6 | 140.2 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 13.5 | 35.7 |
