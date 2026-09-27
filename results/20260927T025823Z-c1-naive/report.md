# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:58:23+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 1963 holders > total=100; buyers were confirmed 1962 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1863 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 1963 holders |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 13 refused otherwise (e.g. 409), 7 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 39578 sold-out answers, 1963/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 48 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 1445 violations in 383 snapshots: {'count_mismatch': 362, 'duplicate_ticket': 362, 'oversell': 361, 'count_decreased': 10, 'user_holds_two': 350} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 31, "users": ["u003115", "u003142", "u003249", "u003495", "u003505", "u003511", "u003575", "u003652", "u003707", "u003721", "u003790", "u003805", "u003835", "u004214", "u004235", "u004293", "u004368", "u004447", "u004530", "u005343", "u005364"]}, {"ticket_no": 62, "users": ["u005228", "u006662", "u006905", "u006924", "u006973", "u007067", "u007084", "u007188", "u007190", "u007229", "u007253", "u007327", "u007341", "u007378", "u007516", "u007540", "u007550", "u007967", "u008021", "u008077", "u008255", "u008357"]}, {"ticket_no": 92, "users": ["u009030", "u009375", "u009485", "u009644", "u009850", "u009913", "u009991", "u010062", "u010072", "u010082", "u010114", "u010168", "u010216", "u010226", "u010270", "u010311"]}]`
- U5: `[{"user_id": "u011046", "request_id": "r011046", "kind": "dup_sequential"}, {"user_id": "u010450", "request_id": "r010450", "kind": "dup_sequential"}, {"user_id": "u010038", "request_id": "r010038", "kind": "replay_after_sellout"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 2.738, "sold": 2, "holders": 64}, {"kind": "duplicate_ticket", "t_s": 2.738, "repeated": 56}, {"kind": "count_mismatch", "t_s": 3.045, "sold": 12, "holders": 132}]`

## Throughput and latency

Stampede: 51000 responses in 49.641 s → **1027.4 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.0 | 24.0 | 557.2 | 1213.7 |
| service time (from actual send) | 1.3 | 23.2 | 524.5 | 1212.7 |
| client send lag | 0.7 | 1.1 | 21.4 | 115.6 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.1 | 233.2 | 637.4 |
| ↳ seller: allocator queries | 0.3 | 2.7 | 156.0 | 1011.0 |
| ↳ seller: whole handler | 0.6 | 12.9 | 394.9 | 1211.7 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.7 | 4.2 | 25.0 | 652.1 |

Responses by HTTP status: `{'200': 1963, '409': 39514, '503': 9523}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 9.662 s  
Seller counters during the run (GET /metrics): `{'admission_shed': 9549}`  
Client health: 4 worker processes, CPU per worker `['14%', '14%', '14%', '14%']` of one core; send lag p99 21.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'turned_away_known': 9309, 'purchased': 1960, 'sold_out': 38731}`. 9360 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 21 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 9523, 'purchased': 1963, 'sold_out': 39514}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 153 | 0 | 0 | 1890 | 0 | 266.4 | 875.8 |
| 1 | 1017 | 0 | 210 | 0 | 0 | 807 | 0 | 1.5 | 514.8 |
| 2 | 1010 | 0 | 206 | 0 | 0 | 804 | 0 | 1.5 | 510.3 |
| 3 | 1017 | 0 | 202 | 0 | 0 | 815 | 0 | 1.6 | 533.2 |
| 4 | 1021 | 0 | 189 | 0 | 0 | 832 | 0 | 1.6 | 562.2 |
| 5 | 1022 | 0 | 179 | 0 | 0 | 843 | 0 | 1.9 | 578.5 |
| 6 | 1020 | 0 | 201 | 0 | 0 | 819 | 0 | 1.7 | 510.1 |
| 7 | 1016 | 0 | 207 | 0 | 0 | 809 | 0 | 1.6 | 499.6 |
| 8 | 1011 | 0 | 206 | 0 | 0 | 805 | 0 | 1.7 | 499.3 |
| 9 | 1019 | 0 | 169 | 15 | 0 | 835 | 0 | 2.2 | 487.7 |
| 10 | 1027 | 0 | 41 | 780 | 0 | 206 | 0 | 2.4 | 230.4 |
| 11 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.4 | 17.4 |
| 12 | 1021 | 0 | 0 | 1004 | 0 | 17 | 0 | 9.3 | 90.6 |
| 13 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.9 | 26.7 |
| 14 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.2 | 53.8 |
| 15 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 1.9 | 15.1 |
| 16 | 1023 | 0 | 0 | 1022 | 0 | 1 | 0 | 2.3 | 64.4 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.0 | 15.4 |
| 18 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.2 | 34.7 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.8 | 52.5 |
| 20 | 1019 | 0 | 0 | 1019 | 0 | 0 | 0 | 1.9 | 16.2 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.1 | 49.3 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 2.0 | 26.2 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.1 | 48.0 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 1.9 | 20.3 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.8 | 40.6 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.9 | 16.5 |
| 27 | 1013 | 0 | 0 | 1013 | 0 | 0 | 0 | 1.8 | 14.8 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 2.1 | 55.8 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.2 | 25.5 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 2.0 | 75.0 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.8 | 16.2 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 2.0 | 52.1 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.0 | 16.7 |
| 34 | 1028 | 0 | 0 | 1028 | 0 | 0 | 0 | 1.9 | 16.0 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.3 | 50.7 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 16.6 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.0 | 47.5 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 16.0 |
| 39 | 1023 | 0 | 0 | 983 | 0 | 40 | 0 | 2.7 | 107.8 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 1.9 | 19.0 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.0 | 16.7 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 2.2 | 61.9 |
| 43 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.0 | 15.9 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.0 | 40.9 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 16.5 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 1.9 | 45.8 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.1 | 58.1 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.0 | 18.6 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 12.5 | 24.7 |
