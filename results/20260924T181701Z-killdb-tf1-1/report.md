# Run `killdb-tf1-1`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 52843 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T18:17:01+00:00 · client retries unclear answers up to 10x with the same request_id

**Fault injected:** kill SIGKILL postgres, restart after 5s, synchronous_commit=on (events relative to t0: {'fault': 5.238, 'restart': 10.784, 'recovered': 14.767}), planned t=5.238–14.767 s, actual t=5.2–14.8 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 15000 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 12893 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 25598 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1063 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 2445 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 221 snapshots over 66.7s, 0 violations (10 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 52843 responses in 63.948 s → **826.3 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 84.9 | 1055.9 | 1373.0 | 2361.6 |
| service time (from actual send) | 47.6 | 1040.0 | 1325.1 | 2280.4 |
| client send lag | 14.6 | 58.8 | 133.6 | 246.5 |
| ↳ seller: waiting for a DB connection | 0.1 | 0.1 | 800.5 | 1000.7 |
| ↳ seller: allocator queries | 2.5 | 13.0 | 78.0 | 716.6 |
| ↳ seller: whole handler | 8.2 | 1001.7 | 1095.1 | 2172.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 27.1 | 103.3 | 1251.4 | 1412.7 |

Responses by HTTP status: `{'200': 15411, '409': 25589, '502': 1, '503': 11842}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 11843}`  
Transport errors: `{'JSONDecodeError': 1}`  
First sold-out answer at t = 22.159 s  
Seller counters during the run (GET /metrics): `{'claims': 5163, 'unique_violation_retries': 15, 'sold_out_fast': 8731}`  
Client health: 4 worker processes, CPU per worker `['68%', '68%', '68%', '68%']` of one core; send lag p99 133.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 15000, 'sold_out': 25000}`. 9652 got at least one unclear answer (503 or no response); **12 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 1563 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 1, 'not_attempted': 11832, 'purchased': 15411, 'sold_out': 25589, 'unknown': 10}`

## Requests in flight at the instant of the fault

656 requests had been sent but not yet answered when the fault hit. What became of each:

- unclear, then sold out on retry: **560**
- unclear, then bought on retry: had NOT committed: **89**
- unclear, then retry found it: HAD committed: **7**

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 2043 | 0 | 0 | 0 | 0 | 1178.7 | 1413.1 |
| 1 | 1030 | 0 | 1030 | 0 | 0 | 0 | 0 | 23.7 | 69.2 |
| 2 | 1017 | 0 | 1017 | 0 | 0 | 0 | 0 | 7.6 | 26.5 |
| 3 | 1027 | 0 | 1027 | 0 | 0 | 0 | 0 | 9.5 | 72.5 |
| 4 | 1067 | 46 | 610 | 0 | 10 | 447 | 0 | 8.9 | 1006.2 |
| 5 ⚡ | 1091 | 62 | 0 | 0 | 0 | 1091 | 0 | 1002.7 | 1033.7 |
| 6 ⚡ | 1418 | 395 | 0 | 0 | 0 | 1418 | 0 | 1003.5 | 1028.3 |
| 7 ⚡ | 1228 | 200 | 0 | 0 | 0 | 1228 | 0 | 1005.1 | 1043.5 |
| 8 ⚡ | 1217 | 200 | 0 | 0 | 0 | 1217 | 0 | 1006.9 | 1032.9 |
| 9 ⚡ | 1224 | 199 | 0 | 0 | 0 | 1224 | 0 | 1018.9 | 1067.5 |
| 10 ⚡ | 1229 | 201 | 0 | 0 | 0 | 1229 | 0 | 1038.5 | 1097.8 |
| 11 ⚡ | 1215 | 201 | 0 | 0 | 0 | 1215 | 0 | 1054.8 | 1232.5 |
| 12 ⚡ | 1234 | 200 | 6 | 0 | 0 | 1228 | 0 | 1110.6 | 1641.8 |
| 13 ⚡ | 1224 | 198 | 91 | 0 | 0 | 1133 | 0 | 1221.2 | 1615.5 |
| 14 ⚡ | 1217 | 202 | 816 | 0 | 0 | 401 | 0 | 1124.7 | 1695.8 |
| 15 | 1233 | 200 | 1232 | 0 | 0 | 1 | 0 | 496.3 | 1039.7 |
| 16 | 1226 | 199 | 1226 | 0 | 0 | 0 | 0 | 156.8 | 405.5 |
| 17 | 1227 | 201 | 1227 | 0 | 0 | 0 | 0 | 79.8 | 168.7 |
| 18 | 1221 | 196 | 1221 | 0 | 0 | 0 | 0 | 86.6 | 217.1 |
| 19 | 1235 | 201 | 1235 | 0 | 0 | 0 | 0 | 88.2 | 232.9 |
| 20 | 1225 | 202 | 1225 | 0 | 0 | 0 | 0 | 80.9 | 226.4 |
| 21 | 1227 | 200 | 1227 | 0 | 0 | 0 | 0 | 92.5 | 286.8 |
| 22 | 1219 | 200 | 110 | 1109 | 0 | 0 | 0 | 48.7 | 180.9 |
| 23 | 1224 | 201 | 3 | 1221 | 0 | 0 | 0 | 86.9 | 277.6 |
| 24 | 1227 | 200 | 0 | 1227 | 0 | 0 | 0 | 56.9 | 204.1 |
| 25 | 1220 | 199 | 1 | 1219 | 0 | 0 | 0 | 45.7 | 201.9 |
| 26 | 1222 | 196 | 0 | 1222 | 0 | 0 | 0 | 93.2 | 373.2 |
| 27 | 1227 | 205 | 0 | 1227 | 0 | 0 | 0 | 42.6 | 160.3 |
| 28 | 1225 | 199 | 0 | 1225 | 0 | 0 | 0 | 42.6 | 177.1 |
| 29 | 1218 | 200 | 2 | 1216 | 0 | 0 | 0 | 44.6 | 222.7 |
| 30 | 1219 | 200 | 1 | 1218 | 0 | 0 | 0 | 43.7 | 185.4 |
| 31 | 1224 | 200 | 1 | 1222 | 0 | 0 | 0 | 136.6 | 478.9 |
| 32 | 1230 | 201 | 0 | 1230 | 0 | 0 | 0 | 63.8 | 263.0 |
| 33 | 1223 | 198 | 0 | 1223 | 0 | 0 | 0 | 109.4 | 442.9 |
| 34 | 1238 | 200 | 1 | 1237 | 0 | 0 | 0 | 256.5 | 547.9 |
| 35 | 1229 | 199 | 2 | 1227 | 0 | 0 | 0 | 47.3 | 225.1 |
| 36 | 1227 | 202 | 3 | 1224 | 0 | 0 | 0 | 48.5 | 226.4 |
| 37 | 1228 | 200 | 3 | 1225 | 0 | 0 | 0 | 39.7 | 177.3 |
| 38 | 1215 | 198 | 4 | 1211 | 0 | 0 | 0 | 38.4 | 243.7 |
| 39 | 214 | 203 | 0 | 214 | 0 | 0 | 0 | 23.2 | 195.4 |
| 40 | 198 | 198 | 3 | 195 | 0 | 0 | 0 | 9.0 | 109.8 |
| 41 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 12.1 | 221.5 |
| 42 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 8.8 | 111.0 |
| 43 | 199 | 199 | 1 | 198 | 0 | 0 | 0 | 19.3 | 213.3 |
| 44 | 201 | 201 | 0 | 201 | 0 | 0 | 0 | 10.5 | 134.0 |
| 45 | 200 | 200 | 4 | 196 | 0 | 0 | 0 | 7.6 | 127.7 |
| 46 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 7.7 | 108.5 |
| 47 | 199 | 199 | 2 | 197 | 0 | 0 | 0 | 6.2 | 139.5 |
| 48 | 201 | 201 | 1 | 200 | 0 | 0 | 0 | 6.1 | 70.8 |
| 49 | 196 | 196 | 2 | 194 | 0 | 0 | 0 | 6.3 | 150.8 |
| 50 | 205 | 205 | 6 | 199 | 0 | 0 | 0 | 5.2 | 96.1 |
| 51 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 5.5 | 126.5 |
| 52 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 4.3 | 89.1 |
| 53 | 200 | 200 | 6 | 194 | 0 | 0 | 0 | 6.0 | 175.7 |
| 54 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 4.0 | 95.4 |
| 55 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 3.7 | 88.8 |
| 56 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 4.6 | 166.0 |
| 57 | 200 | 200 | 4 | 196 | 0 | 0 | 0 | 2.7 | 87.3 |
| 58 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 3.3 | 134.5 |
| 59 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 2.8 | 102.3 |
| 60 | 201 | 201 | 2 | 199 | 0 | 0 | 0 | 2.7 | 91.9 |
| 61 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 2.7 | 131.3 |
| 62 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 2.9 | 93.2 |
| 63 | 139 | 139 | 2 | 137 | 0 | 0 | 0 | 3.4 | 153.7 |

⚡ = fault active (t=5.2–14.8 s)
