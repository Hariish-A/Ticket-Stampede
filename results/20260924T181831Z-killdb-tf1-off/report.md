# Run `killdb-tf1-off`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 52951 requests (burst 1000 at t=0, then 1000.0/s) · seed 4 · 2026-09-24T18:18:31+00:00 · client retries unclear answers up to 10x with the same request_id

**Fault injected:** kill SIGKILL postgres, restart after 5s, synchronous_commit=off (events relative to t0: {'fault': 7.211, 'restart': 12.768, 'recovered': 17.715}), planned t=7.211–17.715 s, actual t=7.2–17.7 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | buyers were confirmed 15002 distinct tickets > total=15000 |
| I2 | Never issue the same ticket number twice | **FAIL** | 2 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 13001 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | 2 tickets confirmed to buyers are missing from /status (phantoms = lost sales) |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 25577 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1064 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 2135 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 228 snapshots over 69.0s, 0 violations (10 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 7355, "users": ["u007354", "u016767"]}, {"ticket_no": 7356, "users": ["u007356", "u016720"]}]`
- I4: `[{"user_id": "u007354", "ticket_no": 7355}, {"user_id": "u007356", "ticket_no": 7356}]`

## Throughput and latency

Stampede: 52951 responses in 66.04 s → **801.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 86.3 | 1078.3 | 1388.1 | 1554.5 |
| service time (from actual send) | 48.6 | 1054.9 | 1377.5 | 1520.5 |
| client send lag | 14.2 | 63.8 | 134.4 | 264.3 |
| ↳ seller: waiting for a DB connection | 0.1 | 0.1 | 879.4 | 1034.3 |
| ↳ seller: allocator queries | 1.6 | 9.7 | 52.4 | 787.0 |
| ↳ seller: whole handler | 6.0 | 1001.9 | 1055.9 | 1190.0 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 30.8 | 101.4 | 1351.7 | 1505.6 |

Responses by HTTP status: `{'200': 15432, '409': 25568, '503': 11951}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 11951}`  
First sold-out answer at t = 22.562 s  
Seller counters during the run (GET /metrics): `{'claims': 5323, 'unique_violation_retries': 22, 'blocking_fallbacks': 4, 'sold_out_fast': 8765, 'sold_out_checks': 4}`  
Client health: 4 worker processes, CPU per worker `['68%', '67%', '68%', '68%']` of one core; send lag p99 134.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 15002, 'sold_out': 24998}`. 9712 got at least one unclear answer (503 or no response); **10 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 1261 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 11940, 'purchased': 15432, 'sold_out': 25568, 'unknown': 11}`

## Requests in flight at the instant of the fault

873 requests had been sent but not yet answered when the fault hit. What became of each:

- unclear, then sold out on retry: **759**
- unclear, then bought on retry: had NOT committed: **99**
- unclear, then retry found it: HAD committed: **15**

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2040 | 0 | 2040 | 0 | 0 | 0 | 0 | 1139.3 | 1519.1 |
| 1 | 1032 | 0 | 1032 | 0 | 0 | 0 | 0 | 25.8 | 99.3 |
| 2 | 1018 | 0 | 1018 | 0 | 0 | 0 | 0 | 3.7 | 31.4 |
| 3 | 1029 | 0 | 1029 | 0 | 0 | 0 | 0 | 4.2 | 55.8 |
| 4 | 1031 | 0 | 1031 | 0 | 0 | 0 | 0 | 4.4 | 61.3 |
| 5 | 1024 | 0 | 1024 | 0 | 0 | 0 | 0 | 3.3 | 41.9 |
| 6 | 1133 | 115 | 360 | 0 | 11 | 762 | 0 | 1002.1 | 1065.2 |
| 7 ⚡ | 1187 | 170 | 0 | 0 | 0 | 1187 | 0 | 1003.2 | 1047.6 |
| 8 ⚡ | 1303 | 275 | 0 | 0 | 0 | 1303 | 0 | 1005.1 | 1039.6 |
| 9 ⚡ | 1228 | 200 | 0 | 0 | 0 | 1228 | 0 | 1007.5 | 1039.7 |
| 10 ⚡ | 1234 | 199 | 0 | 0 | 0 | 1234 | 0 | 1016.2 | 1078.6 |
| 11 ⚡ | 1228 | 201 | 0 | 0 | 0 | 1228 | 0 | 1041.0 | 1150.5 |
| 12 ⚡ | 1228 | 199 | 0 | 0 | 0 | 1228 | 0 | 1058.0 | 1177.9 |
| 13 ⚡ | 1225 | 200 | 0 | 0 | 0 | 1225 | 0 | 1091.4 | 1174.8 |
| 14 ⚡ | 1224 | 201 | 0 | 0 | 0 | 1224 | 0 | 1144.3 | 1333.5 |
| 15 ⚡ | 1223 | 197 | 208 | 0 | 0 | 1015 | 0 | 1178.0 | 1383.3 |
| 16 ⚡ | 1217 | 199 | 930 | 0 | 0 | 287 | 0 | 1119.2 | 1472.9 |
| 17 ⚡ | 1228 | 203 | 1209 | 0 | 0 | 19 | 0 | 612.8 | 1224.9 |
| 18 | 1232 | 199 | 1232 | 0 | 0 | 0 | 0 | 169.0 | 530.6 |
| 19 | 1225 | 201 | 1225 | 0 | 0 | 0 | 0 | 107.9 | 251.8 |
| 20 | 1227 | 200 | 1227 | 0 | 0 | 0 | 0 | 80.7 | 232.5 |
| 21 | 1228 | 200 | 1228 | 0 | 0 | 0 | 0 | 130.4 | 362.2 |
| 22 | 1234 | 200 | 564 | 670 | 0 | 0 | 0 | 93.3 | 273.1 |
| 23 | 1216 | 198 | 3 | 1213 | 0 | 0 | 0 | 97.2 | 292.2 |
| 24 | 1228 | 203 | 1 | 1227 | 0 | 0 | 0 | 117.3 | 327.2 |
| 25 | 1226 | 200 | 5 | 1221 | 0 | 0 | 0 | 68.0 | 214.2 |
| 26 | 1218 | 198 | 2 | 1216 | 0 | 0 | 0 | 89.8 | 337.6 |
| 27 | 1229 | 202 | 0 | 1229 | 0 | 0 | 0 | 93.9 | 259.4 |
| 28 | 1218 | 198 | 3 | 1215 | 0 | 0 | 0 | 48.6 | 213.1 |
| 29 | 1215 | 200 | 0 | 1215 | 0 | 0 | 0 | 78.5 | 230.0 |
| 30 | 1224 | 200 | 3 | 1221 | 0 | 0 | 0 | 79.5 | 286.9 |
| 31 | 1224 | 201 | 4 | 1220 | 0 | 0 | 0 | 42.9 | 205.0 |
| 32 | 1215 | 200 | 1 | 1214 | 0 | 0 | 0 | 57.8 | 246.3 |
| 33 | 1233 | 200 | 0 | 1233 | 0 | 0 | 0 | 69.3 | 259.2 |
| 34 | 1228 | 200 | 2 | 1226 | 0 | 0 | 0 | 65.3 | 217.6 |
| 35 | 1219 | 195 | 1 | 1218 | 0 | 0 | 0 | 43.2 | 201.7 |
| 36 | 1222 | 205 | 2 | 1220 | 0 | 0 | 0 | 46.4 | 248.8 |
| 37 | 1222 | 201 | 2 | 1220 | 0 | 0 | 0 | 45.9 | 178.6 |
| 38 | 1233 | 196 | 2 | 1231 | 0 | 0 | 0 | 58.9 | 288.6 |
| 39 | 212 | 204 | 1 | 211 | 0 | 0 | 0 | 24.0 | 178.8 |
| 40 | 197 | 197 | 1 | 196 | 0 | 0 | 0 | 14.8 | 148.6 |
| 41 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 11.5 | 128.5 |
| 42 | 201 | 201 | 2 | 199 | 0 | 0 | 0 | 11.3 | 151.3 |
| 43 | 202 | 202 | 3 | 199 | 0 | 0 | 0 | 18.0 | 176.6 |
| 44 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 18.8 | 195.3 |
| 45 | 198 | 198 | 1 | 197 | 0 | 0 | 0 | 11.3 | 189.4 |
| 46 | 202 | 202 | 2 | 200 | 0 | 0 | 0 | 9.9 | 184.1 |
| 47 | 197 | 197 | 0 | 197 | 0 | 0 | 0 | 7.7 | 129.3 |
| 48 | 202 | 202 | 5 | 197 | 0 | 0 | 0 | 7.5 | 131.2 |
| 49 | 199 | 199 | 2 | 197 | 0 | 0 | 0 | 7.5 | 188.9 |
| 50 | 199 | 199 | 1 | 198 | 0 | 0 | 0 | 5.7 | 106.7 |
| 51 | 201 | 201 | 0 | 201 | 0 | 0 | 0 | 8.3 | 175.1 |
| 52 | 202 | 202 | 1 | 201 | 0 | 0 | 0 | 6.3 | 96.1 |
| 53 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 8.1 | 167.1 |
| 54 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 6.1 | 146.2 |
| 55 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 4.2 | 92.9 |
| 56 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 5.0 | 180.6 |
| 57 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 3.4 | 87.0 |
| 58 | 200 | 200 | 4 | 196 | 0 | 0 | 0 | 3.1 | 107.0 |
| 59 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 3.4 | 96.5 |
| 60 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 2.5 | 88.5 |
| 61 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 2.8 | 105.5 |
| 62 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 2.6 | 95.4 |
| 63 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 3.2 | 203.4 |
| 64 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 2.7 | 102.3 |
| 65 | 189 | 189 | 2 | 187 | 0 | 0 | 0 | 2.5 | 113.0 |
| 66 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 5.0 | 5.0 |

⚡ = fault active (t=7.2–17.7 s)
