# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:40:21+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 2187 holders > total=100; buyers were confirmed 2184 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 2087 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 5 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 2187 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 5 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 20 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 41056 sold-out answers, 2187/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1162 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 60 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 1216 violations in 324 snapshots: {'count_mismatch': 304, 'oversell': 304, 'duplicate_ticket': 304, 'user_holds_two': 304} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 28, "users": ["u001729", "u001927", "u001977", "u002071", "u002173", "u002194", "u002310", "u002402", "u002411", "u002632", "u002688", "u002741", "u002775", "u002845", "u002868", "u002869", "u002900", "u002979", "u003602", "u003681", "u003686"]}, {"ticket_no": 36, "users": ["u002538", "u002984", "u003031", "u003099", "u003100", "u003104", "u003105", "u003106", "u003187", "u003188", "u003280", "u003326", "u003377", "u003388", "u003450", "u003568", "u003577", "u003594", "u003620", "u003647", "u003678", "u003689", "u003985", "u004033", "u004309"]}, {"ticket_no": 12, "users": ["u001119", "u001249", "u001253", "u001325", "u001334", "u001345", "u001357", "u001385", "u001406"]}]`
- I3: `[{"request_id": "r007127", "tickets": [75, 77]}, {"request_id": "r002081", "tickets": [16, 18]}, {"request_id": "r004135", "tickets": [37, 42]}]`
- U1: `[{"user_id": "u002081", "tickets": [16, 18]}, {"user_id": "u008119", "tickets": [88, 93]}, {"user_id": "u004135", "tickets": [37, 42]}]`
- U5: `[{"user_id": "u001394", "request_id": "r001394", "kind": "replay_after_sellout"}, {"user_id": "u002143", "request_id": "r002143", "kind": "replay_after_sellout"}, {"user_id": "u001979", "request_id": "r001979", "kind": "replay_after_sellout"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 11.002, "sold": 91, "holders": 1967}, {"kind": "oversell", "t_s": 11.002, "sold": 91, "holders": 1967, "total": 100}, {"kind": "duplicate_ticket", "t_s": 11.002, "repeated": 1867}]`

## Throughput and latency

Stampede: 51000 responses in 49.666 s → **1026.9 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 8.6 | 1006.8 | 1734.1 | 1972.9 |
| service time (from actual send) | 7.9 | 1006.0 | 1718.0 | 1971.6 |
| client send lag | 0.7 | 1.1 | 13.6 | 121.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 66.3 | 999.3 | 1055.5 |
| ↳ seller: allocator queries | 0.6 | 5.9 | 134.7 | 572.5 |
| ↳ seller: whole handler | 4.8 | 1000.2 | 1109.7 | 1568.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.2 | 17.2 | 732.5 | 883.4 |

Responses by HTTP status: `{'200': 2187, '409': 40966, '503': 7847}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 8.662 s  
Client health: 4 worker processes, CPU per worker `['16%', '16%', '16%', '16%']` of one core; send lag p99 13.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'purchased': 2179, 'turned_away_known': 7675, 'sold_out': 40146}`. 7732 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 29 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 7847, 'purchased': 2187, 'sold_out': 40966}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 366 | 0 | 0 | 1677 | 0 | 1302.3 | 1880.8 |
| 1 | 1017 | 0 | 248 | 0 | 0 | 769 | 0 | 1003.2 | 1570.1 |
| 2 | 1010 | 0 | 238 | 0 | 0 | 772 | 0 | 1001.9 | 1241.5 |
| 3 | 1017 | 0 | 225 | 0 | 0 | 792 | 0 | 1002.0 | 1228.0 |
| 4 | 1021 | 0 | 254 | 0 | 0 | 767 | 0 | 1002.0 | 1322.7 |
| 5 | 1022 | 0 | 119 | 0 | 0 | 903 | 0 | 1016.5 | 1224.1 |
| 6 | 1020 | 0 | 253 | 0 | 0 | 767 | 0 | 1013.0 | 1266.7 |
| 7 | 1016 | 0 | 249 | 23 | 0 | 744 | 0 | 1002.0 | 1230.8 |
| 8 | 1011 | 0 | 209 | 217 | 0 | 585 | 0 | 1001.9 | 1213.0 |
| 9 | 1019 | 0 | 26 | 922 | 0 | 71 | 0 | 665.1 | 1019.6 |
| 10 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 13.7 | 347.0 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.2 | 24.4 |
| 12 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 2.0 | 71.6 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.1 | 22.5 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 69.5 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 2.1 | 24.6 |
| 16 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 65.9 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.0 | 18.8 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.8 | 65.0 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.4 | 25.2 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 17.2 | 118.7 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.4 | 46.0 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 2.4 | 138.0 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 3.2 | 30.5 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 10.5 | 189.6 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 75.0 | 539.6 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 4.0 | 111.6 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 2.6 | 26.4 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.4 | 111.4 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 4.1 | 47.7 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 6.1 | 85.1 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.2 | 28.1 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 4.4 | 78.6 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.8 | 27.5 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 9.3 | 107.5 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.9 | 41.5 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 67.6 | 415.7 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 40.2 | 237.3 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.8 | 82.2 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 4.3 | 44.3 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 12.9 | 87.0 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 19.2 | 108.0 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.6 | 47.3 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 4.2 | 227.8 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.9 | 79.0 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 3.7 | 114.6 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.5 | 38.3 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.4 | 84.7 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.3 | 23.9 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 11.3 | 49.7 |
