# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-27T02:42:28+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 2494 holders > total=100; buyers were confirmed 2492 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 2394 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 2 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 2494 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 2 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 13 refused otherwise (e.g. 409), 7 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 37494 sold-out answers, 2494/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1164 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 48 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 1333 violations in 355 snapshots: {'count_mismatch': 335, 'duplicate_ticket': 335, 'oversell': 334, 'count_decreased': 13, 'user_holds_two': 316} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 93, "users": ["u009351", "u009991", "u010017", "u010144", "u010195", "u010311", "u010443", "u010585", "u010588", "u010594", "u010597", "u010602", "u010606", "u010612", "u010616", "u010621", "u010624", "u010629", "u010633", "u010639", "u010642", "u011645", "u011647", "u011672", "u011677", "u011683", "u011701", "u011703", "u011716", "u011755", "u011756", "u011840", "u011912", "u011918", "u011982", "u012022", "u012199", "u012208", "u012220", "u012223", "u012228", "u012272", "u012376", "u012382", "u012468"]}, {"ticket_no": 43, "users": ["u003149", "u004270", "u004342", "u004528", "u005089", "u005499", "u005908", "u005922", "u005955", "u005964", "u006020", "u006092", "u006116", "u006130", "u006419", "u006488", "u006640", "u007004", "u007038"]}, {"ticket_no": 17, "users": ["u002535", "u002542", "u002569", "u002820", "u002856", "u002875", "u002958", "u003098", "u003340", "u003352", "u003384", "u003558", "u003613", "u003736", "u003755", "u003770", "u003923", "u004000", "u004174"]}]`
- I3: `[{"request_id": "r013363", "tickets": [99, 100]}, {"request_id": "r007739", "tickets": [64, 67]}]`
- U1: `[{"user_id": "u007739", "tickets": [64, 67]}, {"user_id": "u013363", "tickets": [99, 100]}]`
- U5: `[{"user_id": "u010756", "request_id": "r010756", "kind": "dup_sequential"}, {"user_id": "u013606", "request_id": "r013606", "kind": "dup_concurrent"}, {"user_id": "u003474", "request_id": "r003474", "kind": "replay_after_sellout"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 3.029, "sold": 3, "holders": 64}, {"kind": "duplicate_ticket", "t_s": 3.029, "repeated": 59}, {"kind": "count_mismatch", "t_s": 3.383, "sold": 7, "holders": 127}]`

## Throughput and latency

Stampede: 51000 responses in 49.629 s → **1027.6 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.2 | 58.6 | 1076.7 | 2002.1 |
| service time (from actual send) | 1.4 | 57.7 | 1059.6 | 1988.5 |
| client send lag | 0.7 | 1.1 | 16.2 | 98.7 |
| ↳ seller: waiting for a DB connection | 0.0 | 11.5 | 224.7 | 897.6 |
| ↳ seller: allocator queries | 0.3 | 5.3 | 185.3 | 862.3 |
| ↳ seller: whole handler | 0.8 | 30.8 | 410.8 | 1173.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.8 | 7.8 | 37.0 | 1420.7 |

Responses by HTTP status: `{'200': 2494, '409': 37430, '503': 11076}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 9.693 s  
Seller counters during the run (GET /metrics): `{'admission_shed': 11102}`  
Client health: 4 worker processes, CPU per worker `['15%', '15%', '15%', '15%']` of one core; send lag p99 16.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

50000 buyers (user, request_id): final answers `{'turned_away_known': 10825, 'purchased': 2488, 'sold_out': 36687}`. 10885 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 20 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 11076, 'purchased': 2494, 'sold_out': 37430}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 114 | 0 | 0 | 1929 | 0 | 309.8 | 1432.7 |
| 1 | 1017 | 0 | 166 | 0 | 0 | 851 | 0 | 2.4 | 605.0 |
| 2 | 1010 | 0 | 213 | 0 | 0 | 797 | 0 | 1.5 | 517.8 |
| 3 | 1017 | 0 | 203 | 0 | 0 | 814 | 0 | 1.6 | 510.4 |
| 4 | 1021 | 0 | 210 | 0 | 0 | 811 | 0 | 1.6 | 491.8 |
| 5 | 1022 | 0 | 203 | 0 | 0 | 819 | 0 | 1.7 | 524.6 |
| 6 | 1020 | 0 | 212 | 0 | 0 | 808 | 0 | 1.6 | 491.9 |
| 7 | 1016 | 0 | 217 | 0 | 0 | 799 | 0 | 1.5 | 542.5 |
| 8 | 1011 | 0 | 210 | 0 | 0 | 801 | 0 | 1.6 | 550.4 |
| 9 | 1019 | 0 | 201 | 9 | 0 | 809 | 0 | 1.6 | 540.2 |
| 10 | 1027 | 0 | 207 | 54 | 0 | 766 | 0 | 1.8 | 453.3 |
| 11 | 1014 | 0 | 195 | 152 | 0 | 667 | 0 | 1.8 | 432.7 |
| 12 | 1021 | 0 | 143 | 638 | 0 | 240 | 0 | 15.5 | 246.7 |
| 13 | 1027 | 0 | 0 | 999 | 0 | 28 | 0 | 3.1 | 90.7 |
| 14 | 1017 | 0 | 0 | 996 | 0 | 21 | 0 | 10.5 | 88.1 |
| 15 | 1028 | 0 | 0 | 1020 | 0 | 8 | 0 | 20.8 | 104.9 |
| 16 | 1023 | 0 | 0 | 1021 | 0 | 2 | 0 | 2.6 | 63.2 |
| 17 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 8.4 | 94.5 |
| 18 | 1023 | 0 | 0 | 1013 | 0 | 10 | 0 | 2.5 | 65.9 |
| 19 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 2.2 | 27.3 |
| 20 | 1019 | 0 | 0 | 969 | 0 | 50 | 0 | 2.4 | 120.2 |
| 21 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.0 | 55.5 |
| 22 | 1015 | 0 | 0 | 1015 | 0 | 0 | 0 | 2.1 | 25.8 |
| 23 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.1 | 71.1 |
| 24 | 1022 | 0 | 0 | 1022 | 0 | 0 | 0 | 4.9 | 60.1 |
| 25 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 1.9 | 51.7 |
| 26 | 1021 | 0 | 0 | 1021 | 0 | 0 | 0 | 1.9 | 32.5 |
| 27 | 1013 | 0 | 0 | 1009 | 0 | 4 | 0 | 2.3 | 67.2 |
| 28 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 1.8 | 20.0 |
| 29 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 3.2 | 50.0 |
| 30 | 1009 | 0 | 0 | 1009 | 0 | 0 | 0 | 2.3 | 53.0 |
| 31 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.2 | 26.4 |
| 32 | 1027 | 0 | 0 | 1027 | 0 | 0 | 0 | 1.9 | 46.8 |
| 33 | 1014 | 0 | 0 | 1014 | 0 | 0 | 0 | 2.0 | 28.7 |
| 34 | 1028 | 0 | 0 | 997 | 0 | 31 | 0 | 12.2 | 93.0 |
| 35 | 1025 | 0 | 0 | 1025 | 0 | 0 | 0 | 1.8 | 23.7 |
| 36 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.3 | 54.1 |
| 37 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.0 | 46.5 |
| 38 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.2 | 29.3 |
| 39 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 1.9 | 50.3 |
| 40 | 1012 | 0 | 0 | 1012 | 0 | 0 | 0 | 1.9 | 20.7 |
| 41 | 1023 | 0 | 0 | 1023 | 0 | 0 | 0 | 2.1 | 47.3 |
| 42 | 1016 | 0 | 0 | 1016 | 0 | 0 | 0 | 1.8 | 18.5 |
| 43 | 1018 | 0 | 0 | 1007 | 0 | 11 | 0 | 2.2 | 73.1 |
| 44 | 1018 | 0 | 0 | 1018 | 0 | 0 | 0 | 2.4 | 29.8 |
| 45 | 1020 | 0 | 0 | 1020 | 0 | 0 | 0 | 2.1 | 47.4 |
| 46 | 1026 | 0 | 0 | 1026 | 0 | 0 | 0 | 1.9 | 22.3 |
| 47 | 1024 | 0 | 0 | 1024 | 0 | 0 | 0 | 2.5 | 51.9 |
| 48 | 1017 | 0 | 0 | 1017 | 0 | 0 | 0 | 2.3 | 50.4 |
| 49 | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 11.3 | 13.0 |
