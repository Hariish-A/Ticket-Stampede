# Run `slowdb-tf1-baseline`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 152180 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T18:20:21+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 14440 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 112230 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 21864 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1065 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 29399 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 86 snapshots over 65.5s, 0 violations (81 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 560 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 142763 responses in 62.037 s → **2301.3 req/s** handled; 9417 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1784.1 | 7457.9 | 12341.6 | 15171.1 |
| service time (from actual send) | 1749.4 | 6462.0 | 10191.6 | 12167.6 |
| client send lag | 0.0 | 505.5 | 5355.8 | 7003.9 |
| ↳ seller: waiting for a DB connection | 0.1 | 550.6 | 971.8 | 1130.1 |
| ↳ seller: allocator queries | 7.8 | 23.5 | 124.0 | 1976.0 |
| ↳ seller: whole handler | 1012.0 | 1332.0 | 1580.1 | 3486.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 501.6 | 5922.0 | 8584.5 | 12139.7 |

Responses by HTTP status: `{'0': 9417, '200': 14837, '409': 21857, '502': 43194, '503': 62875}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 111180}`  
Transport errors: `{'TimeoutError': 9417, 'JSONDecodeError': 43194}`  
First sold-out answer at t = 35.891 s  
Seller counters during the run (GET /metrics): `{'claims': 5131, 'unique_violation_retries': 14, 'blocking_fallbacks': 7, 'sold_out_fast': 10959, 'sold_out_checks': 7}`  
Client health: 4 worker processes, CPU per worker `['68%', '70%', '70%', '70%']` of one core; send lag p99 5355.8 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 14439, 'still_unknown': 3440, 'sold_out': 21404, 'turned_away_known': 717}`. 31524 got at least one unclear answer (503 or no response); **4180 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 2916 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 43194, 'no_response': 9417, 'not_attempted': 62816, 'purchased': 14837, 'sold_out': 21857, 'unknown': 59}`

## Requests in flight at the instant of the fault

15 requests had been sent but not yet answered when the fault hit. What became of each:

- unclear, never resolved: **10**
- unclear, then retry found it: HAD committed: **3**
- unclear, then bought on retry: had NOT committed: **1**
- answered: purchased (commit acknowledged before the kill): **1**

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 2043 | 0 | 0 | 0 | 0 | 1492.8 | 1896.6 |
| 1 | 1030 | 0 | 1030 | 0 | 0 | 0 | 0 | 50.6 | 319.3 |
| 2 | 1017 | 0 | 1017 | 0 | 0 | 0 | 0 | 13.4 | 124.2 |
| 3 | 1027 | 0 | 1027 | 0 | 0 | 0 | 0 | 12.0 | 68.3 |
| 4 | 1021 | 0 | 1019 | 0 | 2 | 0 | 0 | 13.8 | 140.1 |
| 5 ⚡ | 1029 | 0 | 3 | 0 | 57 | 969 | 0 | 1002.6 | 3121.8 |
| 6 ⚡ | 1607 | 584 | 0 | 0 | 0 | 1607 | 0 | 1002.6 | 1019.7 |
| 7 ⚡ | 2061 | 1033 | 0 | 0 | 0 | 2061 | 0 | 1005.9 | 1150.2 |
| 8 ⚡ | 2882 | 1865 | 0 | 0 | 0 | 2882 | 0 | 1038.3 | 1292.8 |
| 9 ⚡ | 2981 | 1956 | 0 | 0 | 0 | 2981 | 0 | 1042.5 | 1397.2 |
| 10 ⚡ | 3438 | 2410 | 0 | 0 | 0 | 3438 | 0 | 1049.2 | 1326.6 |
| 11 ⚡ | 3803 | 2789 | 0 | 0 | 0 | 3803 | 0 | 1129.8 | 1526.4 |
| 12 ⚡ | 3974 | 2940 | 0 | 0 | 0 | 3974 | 0 | 1142.2 | 1919.2 |
| 13 ⚡ | 3936 | 2910 | 2 | 0 | 0 | 3632 | 302 | 1136.7 | 7524.1 |
| 14 ⚡ | 4228 | 3213 | 6 | 0 | 0 | 4222 | 0 | 1477.9 | 1926.2 |
| 15 ⚡ | 3734 | 2701 | 0 | 0 | 0 | 2249 | 1485 | 1673.8 | 2263.2 |
| 16 | 4641 | 3614 | 2 | 0 | 0 | 3412 | 1227 | 1637.8 | 2123.5 |
| 17 | 3875 | 2849 | 7 | 0 | 0 | 2824 | 1044 | 1764.1 | 2268.3 |
| 18 | 3490 | 2465 | 4 | 0 | 0 | 3243 | 243 | 1938.5 | 3402.1 |
| 19 | 3560 | 2526 | 4 | 0 | 0 | 2455 | 1101 | 1830.6 | 3268.1 |
| 20 | 3913 | 2890 | 4 | 0 | 0 | 2236 | 1673 | 1823.9 | 2181.4 |
| 21 | 3092 | 2065 | 5 | 0 | 0 | 2663 | 424 | 1766.4 | 3837.2 |
| 22 | 3885 | 2866 | 6 | 0 | 0 | 3335 | 544 | 2711.2 | 3592.9 |
| 23 | 3212 | 2189 | 107 | 0 | 0 | 2226 | 879 | 2817.1 | 9193.7 |
| 24 | 1735 | 708 | 340 | 0 | 0 | 1391 | 4 | 6396.6 | 8872.5 |
| 25 | 3241 | 2220 | 411 | 25 | 0 | 2567 | 65 | 6972.7 | 13777.2 |
| 26 | 2773 | 1747 | 485 | 88 | 0 | 1263 | 68 | 6970.9 | 14232.7 |
| 27 | 1491 | 469 | 240 | 93 | 0 | 94 | 3 | 11538.9 | 14116.4 |
| 28 | 1920 | 894 | 561 | 99 | 0 | 99 | 0 | 10345.2 | 13119.6 |
| 29 | 1816 | 798 | 668 | 87 | 0 | 127 | 0 | 8699.4 | 12135.2 |
| 30 | 2309 | 1290 | 752 | 122 | 0 | 331 | 0 | 7282.2 | 11825.6 |
| 31 | 1769 | 745 | 490 | 95 | 0 | 255 | 0 | 6561.3 | 11347.1 |
| 32 | 1684 | 655 | 244 | 108 | 0 | 43 | 10 | 8074.8 | 12223.6 |
| 33 | 3157 | 2132 | 210 | 182 | 0 | 41 | 59 | 3410.4 | 11945.1 |
| 34 | 2260 | 1222 | 121 | 176 | 0 | 13 | 0 | 6105.0 | 9451.1 |
| 35 | 1391 | 361 | 12 | 77 | 0 | 0 | 0 | 6647.7 | 8520.3 |
| 36 | 2899 | 1874 | 28 | 174 | 0 | 10 | 12 | 3095.6 | 13282.1 |
| 37 | 3602 | 2574 | 73 | 204 | 0 | 12 | 44 | 2104.6 | 11106.1 |
| 38 | 2914 | 1897 | 49 | 233 | 0 | 12 | 158 | 1832.6 | 14744.1 |
| 39 | 3190 | 3179 | 33 | 180 | 0 | 0 | 0 | 1430.8 | 2042.0 |
| 40 | 2548 | 2548 | 24 | 146 | 0 | 0 | 0 | 1399.0 | 2055.6 |
| 41 | 5183 | 5183 | 63 | 268 | 0 | 0 | 0 | 1293.2 | 1933.4 |
| 42 | 4179 | 4179 | 262 | 1098 | 0 | 75 | 0 | 1341.2 | 4718.8 |
| 43 | 3756 | 3756 | 455 | 2324 | 0 | 82 | 0 | 2009.8 | 5960.9 |
| 44 | 5534 | 5534 | 382 | 3499 | 0 | 641 | 0 | 4275.1 | 7276.2 |
| 45 | 7486 | 7486 | 338 | 1785 | 0 | 432 | 0 | 2181.1 | 7109.7 |
| 46 | 2670 | 2670 | 278 | 1139 | 0 | 276 | 14 | 2562.3 | 8697.5 |
| 47 | 2324 | 2324 | 257 | 1315 | 0 | 85 | 58 | 641.5 | 9444.1 |
| 48 | 2773 | 2773 | 380 | 2381 | 0 | 12 | 0 | 5616.6 | 7287.0 |
| 49 | 2951 | 2951 | 425 | 2193 | 0 | 333 | 0 | 6157.4 | 8371.6 |
| 50 | 2917 | 2917 | 429 | 2083 | 0 | 405 | 0 | 1029.6 | 7956.1 |
| 51 | 1045 | 1045 | 316 | 724 | 0 | 5 | 0 | 301.2 | 7771.9 |
| 52 | 337 | 337 | 80 | 257 | 0 | 0 | 0 | 23.3 | 256.3 |
| 53 | 463 | 463 | 55 | 408 | 0 | 0 | 0 | 33.5 | 308.8 |
| 54 | 238 | 238 | 59 | 179 | 0 | 0 | 0 | 19.0 | 249.9 |
| 55 | 85 | 85 | 14 | 71 | 0 | 0 | 0 | 14.6 | 211.2 |
| 59 | 8 | 8 | 2 | 6 | 0 | 0 | 0 | 5.5 | 104.0 |
| 60 | 29 | 29 | 8 | 21 | 0 | 0 | 0 | 4.7 | 15.2 |
| 61 | 23 | 23 | 6 | 17 | 0 | 0 | 0 | 4.6 | 86.2 |
| 62 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 6.0 | 6.0 |

⚡ = fault active (t=5.0–15.0 s)
