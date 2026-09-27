# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:36:11+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 2454 holders > total=100; buyers were confirmed 2450 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 2354 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 5 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 2454 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 5 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 20 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 33885 sold-out answers, 2454/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1159 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 61 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 902 violations in 245 snapshots: {'count_mismatch': 225, 'oversell': 225, 'duplicate_ticket': 225, 'user_holds_two': 225, 'count_decreased': 2} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 3 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 18, "users": ["u002150", "u002154", "u002160", "u002255", "u002274", "u002316", "u002322", "u002323", "u002328", "u002334", "u002337", "u002343", "u002359", "u002372", "u002380", "u002386", "u002419", "u002422", "u002475", "u002773"]}, {"ticket_no": 92, "users": ["u009262", "u011269", "u011918", "u012029", "u012133", "u012381", "u012386", "u012422", "u012586", "u012625", "u012632", "u012717", "u012726", "u012829", "u013395", "u013430", "u013793", "u013816", "u013831", "u013859", "u013923", "u013924", "u013995", "u014132", "u014135", "u014138", "u014146", "u014189", "u014232", "u014390", "u014516", "u014556", "u014649", "u014700", "u014824", "u015185"]}, {"ticket_no": 69, "users": ["u007733", "u007961", "u008234", "u008262", "u008347", "u008425", "u008825", "u009473", "u009513", "u009680", "u009756", "u009790", "u009796", "u009890", "u010147", "u010152", "u010230", "u010322", "u010379", "u010466", "u011106", "u011476", "u011617", "u011783"]}]`
- I3: `[{"request_id": "r002315", "tickets": [15, 17]}, {"request_id": "r001667", "tickets": [7, 11]}, {"request_id": "r010915", "tickets": [52, 77]}]`
- U1: `[{"user_id": "u001667", "tickets": [7, 11]}, {"user_id": "u000374", "tickets": [3, 12]}, {"user_id": "u013484", "tickets": [84, 86]}]`
- U5: `[{"user_id": "u016228", "request_id": "r016228", "kind": "dup_sequential"}, {"user_id": "u002296", "request_id": "r002296", "kind": "replay_after_sellout"}, {"user_id": "u002556", "request_id": "r002556", "kind": "replay_after_sellout"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 5.441, "sold": 28, "holders": 575}, {"kind": "oversell", "t_s": 5.441, "sold": 28, "holders": 575, "total": 100}, {"kind": "duplicate_ticket", "t_s": 5.441, "repeated": 533}]`

## Throughput and latency

Stampede: 51000 responses in 49.65 s → **1027.2 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 10.9 | 439.3 | 1211.7 | 3018.6 |
| service time (from actual send) | 10.2 | 438.1 | 1209.6 | 3017.6 |
| client send lag | 0.8 | 1.2 | 24.3 | 143.9 |
| ↳ seller: waiting for a DB connection | 0.0 | 285.8 | 997.2 | 1008.4 |
| ↳ seller: allocator queries | 2.6 | 10.5 | 225.6 | 1438.4 |
| ↳ seller: whole handler | 14.9 | 683.6 | 1182.5 | 3016.1 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 3.5 | 17.4 | 102.9 | 868.5 |

Responses by HTTP status: `{'200': 2451, '409': 33795, '503': 14754}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 9.916 s  
Seller counters during the run (GET /metrics): `{'admission_shed': 13517}`  
Client health: 4 worker processes, CPU per worker `['20%', '20%', '20%', '20%']` of one core; send lag p99 24.3 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'turned_away_known': 14416, 'purchased': 2444, 'still_unknown': 3, 'sold_out': 33137}`. 14482 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 15 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 14751, 'purchased': 2451, 'sold_out': 33795, 'unknown': 3}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 179 | 0 | 0 | 1864 | 0 | 574.7 | 1508.4 |
| 1 | 1017 | 0 | 296 | 0 | 0 | 721 | 0 | 2.7 | 1237.7 |
| 2 | 1010 | 0 | 108 | 0 | 2 | 900 | 0 | 1.8 | 1645.9 |
| 3 | 1017 | 0 | 46 | 0 | 1 | 970 | 0 | 1.9 | 1737.7 |
| 4 | 1021 | 0 | 55 | 0 | 0 | 966 | 0 | 1.7 | 1463.7 |
| 5 | 1022 | 0 | 188 | 0 | 0 | 834 | 0 | 1.8 | 1259.6 |
| 6 | 1020 | 0 | 181 | 0 | 0 | 839 | 0 | 1.7 | 1328.8 |
| 7 | 1016 | 0 | 181 | 0 | 0 | 835 | 0 | 1.9 | 1367.7 |
| 8 | 1011 | 0 | 179 | 2 | 0 | 830 | 0 | 1.8 | 1358.5 |
| 9 | 1019 | 0 | 176 | 1 | 0 | 842 | 0 | 1.9 | 1283.7 |
| 10 | 1027 | 0 | 176 | 0 | 0 | 851 | 0 | 2.0 | 1359.0 |
| 11 | 1014 | 0 | 171 | 7 | 0 | 836 | 0 | 1.7 | 1332.5 |
| 12 | 1021 | 0 | 162 | 2 | 0 | 857 | 0 | 1.8 | 1275.1 |
| 13 | 1027 | 0 | 206 | 38 | 0 | 783 | 0 | 1.9 | 1361.3 |
| 14 | 1017 | 0 | 104 | 162 | 0 | 751 | 0 | 1.7 | 1164.2 |
| 15 | 1028 | 0 | 41 | 330 | 0 | 657 | 0 | 3.1 | 720.2 |
| 16 | 1023 | 0 | 2 | 1021 | 0 | 0 | 0 | 24.8 | 220.6 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 8.8 | 102.9 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.3 | 27.0 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.3 | 73.1 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 2.7 | 35.7 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 93.0 | 274.2 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 14.9 | 73.3 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.7 | 26.4 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 6.7 | 111.7 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.7 | 86.8 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 3.3 | 80.5 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 13.7 | 104.1 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 5.4 | 38.0 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 113.8 | 526.6 |
| 30 | 1009 | 0 | 0 | 1004 | 0 | 5 | 0 | 112.6 | 452.5 |
| 31 | 1023 | 0 | 0 | 912 | 0 | 111 | 0 | 277.2 | 786.7 |
| 32 | 1027 | 0 | 0 | 917 | 0 | 110 | 0 | 134.0 | 552.6 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 31.0 | 225.9 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 19.1 | 68.2 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.6 | 34.5 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 20.3 | 109.6 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 13.2 | 106.1 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 4.0 | 65.6 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 20.7 | 83.3 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 4.1 | 38.7 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 41.2 | 375.3 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.7 | 45.1 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.5 | 66.3 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 12.4 | 88.7 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 169.0 | 561.3 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 45.1 | 392.2 |
| 47 | 1024 | 0 | 0 | 1023 | 0 | 1 | 0 | 158.0 | 629.2 |
| 48 | 1017 | 0 | 0 | 829 | 0 | 188 | 0 | 215.0 | 736.3 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 20.8 | 165.8 |
