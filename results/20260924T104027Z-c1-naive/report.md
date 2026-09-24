# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T10:40:27+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 1837 holders > total=100; buyers were confirmed 1836 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1737 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 8 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 1837 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 8 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 20 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 43078 sold-out answers, 1837/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 857 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 64 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 1220 violations in 325 snapshots: {'count_mismatch': 305, 'oversell': 305, 'duplicate_ticket': 305, 'user_holds_two': 305} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 74, "users": ["u003979", "u004074", "u004081", "u004110", "u004135", "u004151", "u004153", "u004157", "u004161", "u004162", "u004186", "u004187", "u004290", "u005119", "u005186"]}, {"ticket_no": 54, "users": ["u002996", "u003138", "u003144", "u003154", "u003218", "u003221", "u003232", "u003266", "u003277", "u003300", "u003312", "u003332", "u003348", "u003412", "u003483", "u004148", "u004197", "u004199"]}, {"ticket_no": 87, "users": ["u004336", "u004390", "u004517", "u004542", "u004556", "u004594", "u004595"]}]`
- I3: `[{"request_id": "r002004", "tickets": [12, 24]}, {"request_id": "r001010", "tickets": [3, 9]}, {"request_id": "r001582", "tickets": [9, 20]}]`
- U1: `[{"user_id": "u000811", "tickets": [8, 20]}, {"user_id": "u001010", "tickets": [3, 9]}, {"user_id": "u004811", "tickets": [91, 93]}]`
- U5: `[{"user_id": "u005454", "request_id": "r005454", "kind": "fresh"}, {"user_id": "u005167", "request_id": "r005167", "kind": "dup_sequential"}, {"user_id": "u004907", "request_id": "r004907", "kind": "dup_sequential"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 4.507, "sold": 38, "holders": 696}, {"kind": "oversell", "t_s": 4.507, "sold": 38, "holders": 696, "total": 100}, {"kind": "duplicate_ticket", "t_s": 4.507, "repeated": 653}]`

## Throughput and latency

Stampede: 51000 responses in 49.697 s → **1026.2 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 5.9 | 1052.1 | 1883.0 | 2665.9 |
| service time (from actual send) | 5.2 | 1051.3 | 1866.7 | 2665.3 |
| client send lag | 0.7 | 1.2 | 21.4 | 90.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 575.1 | 999.1 | 1023.8 |
| ↳ seller: allocator queries | 0.4 | 6.2 | 82.5 | 804.2 |
| ↳ seller: whole handler | 3.2 | 1000.7 | 1503.2 | 2608.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.1 | 53.6 | 797.4 | 1104.1 |

Responses by HTTP status: `{'200': 1837, '409': 42988, '503': 6175}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 5.008 s  
Client health: 4 worker processes, CPU per worker `['18%', '18%', '18%', '18%']` of one core; send lag p99 21.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'turned_away_known': 5999, 'purchased': 1824, 'sold_out': 42177}`. 6093 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 18 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 6175, 'purchased': 1837, 'sold_out': 42988}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 409 | 0 | 0 | 1634 | 0 | 1265.2 | 1679.8 |
| 1 | 1017 | 0 | 399 | 0 | 0 | 618 | 0 | 1009.7 | 1214.5 |
| 2 | 1010 | 0 | 394 | 0 | 0 | 616 | 0 | 1002.5 | 1176.4 |
| 3 | 1017 | 0 | 400 | 0 | 0 | 617 | 0 | 1002.9 | 1148.7 |
| 4 | 1021 | 0 | 220 | 495 | 0 | 306 | 0 | 1000.5 | 1128.7 |
| 5 | 1022 | 0 | 15 | 1007 | 0 | 0 | 0 | 346.9 | 929.3 |
| 6 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.0 | 75.3 |
| 7 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 1.8 | 14.7 |
| 8 | 1011 | 0 | 0 | 1011 | 0 | 0 | 0 | 1.9 | 60.3 |
| 9 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 1.8 | 18.1 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.0 | 19.1 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.2 | 106.8 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.9 | 16.7 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 1.9 | 59.6 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 1.9 | 15.5 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 1.9 | 15.3 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 59.6 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.0 | 18.2 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.1 | 61.3 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 1.9 | 16.4 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.0 | 16.2 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.4 | 136.9 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 1.8 | 14.3 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.0 | 74.1 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 1.9 | 15.7 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.1 | 68.7 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.8 | 15.8 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 2.1 | 22.5 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.0 | 57.3 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 1.8 | 17.8 |
| 30 | 1009 | 0 | 0 | 1007 | 0 | 2 | 0 | 2.3 | 550.6 |
| 31 | 1023 | 0 | 0 | 814 | 0 | 209 | 0 | 538.0 | 1095.6 |
| 32 | 1027 | 0 | 0 | 754 | 0 | 273 | 0 | 928.1 | 1314.9 |
| 33 | 1014 | 0 | 0 | 451 | 0 | 563 | 0 | 1757.6 | 2206.0 |
| 34 | 1028 | 0 | 0 | 556 | 0 | 472 | 0 | 1742.0 | 2105.5 |
| 35 | 1025 | 0 | 0 | 323 | 0 | 702 | 0 | 1329.1 | 1614.4 |
| 36 | 1020 | 0 | 0 | 877 | 0 | 143 | 0 | 609.6 | 1152.6 |
| 37 | 1024 | 0 | 0 | 1004 | 0 | 20 | 0 | 349.9 | 1024.2 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 71.5 | 607.7 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 3.1 | 144.4 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 28.1 | 147.7 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 192.4 | 589.1 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 10.1 | 233.2 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 18.7 | 286.6 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 15.4 | 236.3 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.1 | 47.9 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 3.0 | 107.8 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 3.8 | 41.6 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 5.8 | 130.2 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 19.7 | 81.5 |
