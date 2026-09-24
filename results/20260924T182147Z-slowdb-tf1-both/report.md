# Run `slowdb-tf1-both`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 54940 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T18:21:47+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 15000 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 14990 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 25590 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1066 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 2801 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 230 snapshots over 75.7s, 0 violations (9 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 54940 responses in 73.092 s → **751.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 97.1 | 344.4 | 1609.5 | 3161.2 |
| service time (from actual send) | 59.3 | 257.1 | 1587.7 | 3160.2 |
| client send lag | 23.0 | 100.4 | 171.6 | 249.8 |
| ↳ seller: waiting for a DB connection | 0.1 | 9.0 | 194.6 | 995.3 |
| ↳ seller: allocator queries | 6.0 | 21.0 | 113.7 | 489.4 |
| ↳ seller: whole handler | 10.8 | 103.7 | 1019.4 | 3087.3 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 54.9 | 140.2 | 1534.8 | 1632.0 |

Responses by HTTP status: `{'200': 15420, '409': 25580, '502': 6, '503': 13934}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 13940}`  
Transport errors: `{'JSONDecodeError': 6}`  
First sold-out answer at t = 23.641 s  
Seller counters during the run (GET /metrics): `{'claims': 4608, 'unique_violation_retries': 15, 'blocking_fallbacks': 7, 'sold_out_fast': 8599, 'sold_out_checks': 7, 'admission_shed': 3912}`  
Client health: 4 worker processes, CPU per worker `['74%', '74%', '73%', '74%']` of one core; send lag p99 171.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 15000, 'sold_out': 25000}`. 11370 got at least one unclear answer (503 or no response); **48 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 1833 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 6, 'not_attempted': 13874, 'purchased': 15420, 'sold_out': 25580, 'unknown': 60}`

## Requests in flight at the instant of the fault

14 requests had been sent but not yet answered when the fault hit. What became of each:

- unclear, then sold out on retry: **7**
- unclear, then retry found it: HAD committed: **6**
- answered: purchased (commit acknowledged before the kill): **1**

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 1827 | 0 | 0 | 216 | 0 | 1399.1 | 1837.0 |
| 1 | 1204 | 174 | 1098 | 0 | 0 | 106 | 0 | 71.8 | 302.8 |
| 2 | 1204 | 187 | 1163 | 0 | 0 | 41 | 0 | 16.8 | 182.4 |
| 3 | 1029 | 2 | 1029 | 0 | 0 | 0 | 0 | 9.4 | 43.5 |
| 4 | 1021 | 0 | 1014 | 0 | 7 | 0 | 0 | 10.8 | 135.5 |
| 5 ⚡ | 1332 | 303 | 0 | 0 | 53 | 1279 | 0 | 1.5 | 3108.8 |
| 6 ⚡ | 1223 | 200 | 0 | 0 | 0 | 1223 | 0 | 1.9 | 1009.1 |
| 7 ⚡ | 1228 | 200 | 0 | 0 | 0 | 1228 | 0 | 3.6 | 1059.7 |
| 8 ⚡ | 1217 | 200 | 0 | 0 | 0 | 1217 | 0 | 6.1 | 1120.9 |
| 9 ⚡ | 1225 | 200 | 0 | 0 | 0 | 1225 | 0 | 25.9 | 1234.0 |
| 10 ⚡ | 1228 | 200 | 0 | 0 | 0 | 1228 | 0 | 65.8 | 1233.6 |
| 11 ⚡ | 1214 | 200 | 0 | 0 | 0 | 1214 | 0 | 48.0 | 1102.2 |
| 12 ⚡ | 1233 | 199 | 0 | 0 | 0 | 1233 | 0 | 50.0 | 1109.5 |
| 13 ⚡ | 1227 | 201 | 0 | 0 | 0 | 1227 | 0 | 59.0 | 1188.8 |
| 14 ⚡ | 1215 | 200 | 9 | 0 | 0 | 1206 | 0 | 93.6 | 1654.3 |
| 15 ⚡ | 1232 | 199 | 487 | 0 | 0 | 739 | 0 | 860.7 | 1547.3 |
| 16 | 1224 | 197 | 763 | 0 | 0 | 461 | 0 | 285.0 | 1126.2 |
| 17 | 1229 | 203 | 1212 | 0 | 0 | 17 | 0 | 232.6 | 446.3 |
| 18 | 1224 | 199 | 1224 | 0 | 0 | 0 | 0 | 179.1 | 364.4 |
| 19 | 1234 | 200 | 1234 | 0 | 0 | 0 | 0 | 205.5 | 395.3 |
| 20 | 1223 | 200 | 1223 | 0 | 0 | 0 | 0 | 174.4 | 326.9 |
| 21 | 1228 | 201 | 1219 | 0 | 0 | 9 | 0 | 181.0 | 487.4 |
| 22 | 1218 | 199 | 1213 | 0 | 0 | 5 | 0 | 236.9 | 549.9 |
| 23 | 1225 | 202 | 611 | 614 | 0 | 0 | 0 | 139.3 | 319.1 |
| 24 | 1227 | 200 | 2 | 1225 | 0 | 0 | 0 | 140.9 | 428.5 |
| 25 | 1220 | 199 | 5 | 1215 | 0 | 0 | 0 | 118.9 | 294.4 |
| 26 | 1226 | 200 | 3 | 1223 | 0 | 0 | 0 | 93.8 | 287.8 |
| 27 | 1220 | 198 | 0 | 1220 | 0 | 0 | 0 | 221.4 | 514.6 |
| 28 | 1228 | 202 | 1 | 1227 | 0 | 0 | 0 | 129.4 | 343.8 |
| 29 | 1217 | 199 | 2 | 1215 | 0 | 0 | 0 | 104.5 | 289.1 |
| 30 | 1221 | 202 | 2 | 1219 | 0 | 0 | 0 | 106.0 | 328.3 |
| 31 | 1224 | 200 | 3 | 1221 | 0 | 0 | 0 | 96.8 | 283.2 |
| 32 | 1227 | 198 | 1 | 1226 | 0 | 0 | 0 | 191.2 | 431.5 |
| 33 | 1227 | 202 | 4 | 1223 | 0 | 0 | 0 | 113.2 | 273.6 |
| 34 | 1229 | 191 | 1 | 1228 | 0 | 0 | 0 | 89.1 | 254.7 |
| 35 | 1238 | 208 | 1 | 1237 | 0 | 0 | 0 | 115.2 | 313.9 |
| 36 | 1226 | 201 | 1 | 1225 | 0 | 0 | 0 | 76.9 | 254.7 |
| 37 | 1225 | 197 | 1 | 1224 | 0 | 0 | 0 | 132.4 | 371.9 |
| 38 | 1215 | 198 | 2 | 1213 | 0 | 0 | 0 | 166.7 | 449.9 |
| 39 | 216 | 205 | 1 | 215 | 0 | 0 | 0 | 28.1 | 150.0 |
| 40 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 41.2 | 281.1 |
| 41 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 37.5 | 240.6 |
| 42 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 37.8 | 258.1 |
| 43 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 32.5 | 206.7 |
| 44 | 199 | 199 | 3 | 196 | 0 | 0 | 0 | 33.8 | 237.1 |
| 45 | 201 | 201 | 2 | 199 | 0 | 0 | 0 | 24.7 | 190.2 |
| 46 | 200 | 200 | 5 | 195 | 0 | 0 | 0 | 19.1 | 142.8 |
| 47 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 27.2 | 219.6 |
| 48 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 18.5 | 156.7 |
| 49 | 195 | 195 | 0 | 195 | 0 | 0 | 0 | 13.3 | 202.5 |
| 50 | 205 | 205 | 3 | 202 | 0 | 0 | 0 | 13.0 | 141.3 |
| 51 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 10.0 | 128.0 |
| 52 | 199 | 199 | 1 | 198 | 0 | 0 | 0 | 9.6 | 170.2 |
| 53 | 201 | 201 | 2 | 199 | 0 | 0 | 0 | 10.4 | 112.7 |
| 54 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 8.3 | 134.7 |
| 55 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 9.0 | 149.6 |
| 56 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 7.1 | 159.0 |
| 57 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 9.7 | 139.0 |
| 58 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 8.0 | 149.4 |
| 59 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 6.4 | 93.6 |
| 60 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 7.4 | 127.9 |
| 61 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 5.3 | 109.8 |
| 62 | 200 | 200 | 0 | 200 | 0 | 0 | 0 | 4.8 | 98.3 |
| 63 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 5.2 | 144.5 |
| 64 | 200 | 200 | 3 | 197 | 0 | 0 | 0 | 4.5 | 92.0 |
| 65 | 200 | 200 | 6 | 194 | 0 | 0 | 0 | 4.7 | 103.6 |
| 66 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 4.1 | 97.4 |
| 67 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 5.1 | 160.1 |
| 68 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 3.9 | 87.2 |
| 69 | 200 | 200 | 2 | 198 | 0 | 0 | 0 | 4.1 | 129.3 |
| 70 | 200 | 200 | 1 | 199 | 0 | 0 | 0 | 5.6 | 168.9 |
| 71 | 176 | 176 | 2 | 174 | 0 | 0 | 0 | 3.8 | 105.2 |
| 72 | 93 | 93 | 1 | 92 | 0 | 0 | 0 | 4.0 | 129.9 |
| 73 | 5 | 5 | 0 | 5 | 0 | 0 | 0 | 7.0 | 30.9 |

⚡ = fault active (t=5.0–15.0 s)
