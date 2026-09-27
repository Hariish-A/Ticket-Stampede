# Run `slowdb-failfast-256`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 250946 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-27T02:38:21+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 14127 confirmed, 14319 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 210996 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=14319 = 14319 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 14319/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1161 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 52285 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 84 snapshots over 54.6s, 0 violations (15 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 192 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 248672 responses in 51.199 s → **4856.9 req/s** handled; 2274 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 25.6 | 249.0 | 1176.2 | 10334.5 |
| service time (from actual send) | 25.2 | 245.0 | 1170.8 | 10334.5 |
| client send lag | 0.0 | 0.8 | 21.0 | 260.1 |
| ↳ seller: waiting for a DB connection | 331.3 | 851.3 | 988.9 | 1002.4 |
| ↳ seller: allocator queries | 17.1 | 58.8 | 202.8 | 524.1 |
| ↳ seller: whole handler | 668.1 | 1045.6 | 1235.7 | 3657.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 13.4 | 104.1 | 340.9 | 2524.0 |

Responses by HTTP status: `{'0': 2274, '200': 14321, '503': 234351}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 209946}`  
Transport errors: `{'TimeoutError': 2274}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 14310, 'unique_violation_retries': 2, 'admission_shed': 231045}`  
Client health: 4 worker processes, CPU per worker `['54%', '52%', '52%', '52%']` of one core; send lag p99 21.0 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'turned_away_known': 23861, 'purchased': 14121, 'still_unknown': 2018}`. 38014 got at least one unclear answer (503 or no response); **45 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 12067 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'no_response': 2274, 'not_attempted': 234338, 'purchased': 14321, 'unknown': 13}`

## Requests in flight at the instant of the fault

267 requests had been sent but not yet answered when the fault hit. What became of each:

- unclear, never resolved: **246**
- answered: purchased (commit acknowledged before the kill): **13**
- unclear, then bought on retry: had NOT committed: **7**
- unclear, then retry found it: HAD committed: **1**

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2689 | 646 | 446 | 0 | 0 | 2243 | 0 | 204.6 | 2560.6 |
| 1 | 2823 | 1793 | 797 | 0 | 0 | 2026 | 0 | 6.5 | 979.1 |
| 2 | 3062 | 2045 | 673 | 0 | 0 | 2389 | 0 | 7.3 | 1007.2 |
| 3 | 3364 | 2337 | 685 | 0 | 0 | 2679 | 0 | 7.7 | 1009.0 |
| 4 | 3195 | 2174 | 429 | 0 | 13 | 2753 | 0 | 9.1 | 1026.6 |
| 5 ⚡ | 3501 | 2472 | 0 | 0 | 0 | 3501 | 0 | 0.8 | 1015.6 |
| 6 ⚡ | 4125 | 3102 | 0 | 0 | 0 | 4125 | 0 | 1.3 | 1010.2 |
| 7 ⚡ | 4448 | 3420 | 0 | 0 | 0 | 4448 | 0 | 1.0 | 1019.3 |
| 8 ⚡ | 4929 | 3912 | 0 | 0 | 0 | 4929 | 0 | 3.8 | 1033.0 |
| 9 ⚡ | 5211 | 4186 | 0 | 0 | 0 | 5211 | 0 | 1.8 | 1150.9 |
| 10 ⚡ | 5458 | 4430 | 0 | 0 | 0 | 5458 | 0 | 97.7 | 1316.0 |
| 11 ⚡ | 5530 | 4516 | 0 | 0 | 0 | 5530 | 0 | 2.1 | 1052.2 |
| 12 ⚡ | 6290 | 5256 | 0 | 0 | 0 | 6290 | 0 | 1.3 | 1078.8 |
| 13 ⚡ | 6446 | 5420 | 0 | 0 | 0 | 6446 | 0 | 6.0 | 1097.9 |
| 14 ⚡ | 6801 | 5786 | 4 | 0 | 0 | 6797 | 0 | 1.4 | 1295.6 |
| 15 ⚡ | 5770 | 4737 | 71 | 0 | 0 | 4495 | 1204 | 419.8 | 9611.5 |
| 16 | 6275 | 5248 | 295 | 0 | 0 | 5001 | 979 | 40.8 | 952.2 |
| 17 | 6095 | 5069 | 273 | 0 | 0 | 5822 | 0 | 24.6 | 957.4 |
| 18 | 5669 | 4644 | 296 | 0 | 0 | 5373 | 0 | 20.8 | 1024.4 |
| 19 | 6281 | 5247 | 98 | 0 | 0 | 6183 | 0 | 21.4 | 1155.6 |
| 20 | 6192 | 5169 | 211 | 0 | 0 | 5981 | 0 | 120.0 | 1093.7 |
| 21 | 6192 | 5165 | 286 | 0 | 0 | 5906 | 0 | 17.7 | 1028.2 |
| 22 | 6260 | 5241 | 121 | 0 | 0 | 6139 | 0 | 31.8 | 1157.7 |
| 23 | 6240 | 5217 | 252 | 0 | 0 | 5988 | 0 | 48.9 | 1042.3 |
| 24 | 6403 | 5376 | 142 | 0 | 0 | 6261 | 0 | 20.6 | 1066.7 |
| 25 | 6263 | 5242 | 288 | 0 | 0 | 5975 | 0 | 26.9 | 1073.0 |
| 26 | 6926 | 5900 | 172 | 0 | 0 | 6754 | 0 | 41.5 | 1125.8 |
| 27 | 7081 | 6059 | 113 | 0 | 0 | 6968 | 0 | 50.4 | 1097.3 |
| 28 | 7147 | 6121 | 149 | 0 | 0 | 6998 | 0 | 33.8 | 1257.3 |
| 29 | 7418 | 6400 | 46 | 0 | 0 | 7372 | 0 | 147.8 | 1314.4 |
| 30 | 6731 | 5712 | 99 | 0 | 0 | 6541 | 91 | 188.6 | 1198.3 |
| 31 | 7101 | 6077 | 280 | 0 | 0 | 6821 | 0 | 36.0 | 964.8 |
| 32 | 6931 | 5902 | 233 | 0 | 0 | 6698 | 0 | 18.9 | 1075.9 |
| 33 | 7477 | 6452 | 239 | 0 | 0 | 7238 | 0 | 36.8 | 1071.3 |
| 34 | 7362 | 6324 | 215 | 0 | 0 | 7147 | 0 | 30.0 | 960.9 |
| 35 | 6780 | 5750 | 229 | 0 | 0 | 6551 | 0 | 16.0 | 1133.6 |
| 36 | 6502 | 5477 | 157 | 0 | 0 | 6345 | 0 | 65.9 | 1089.8 |
| 37 | 7431 | 6403 | 263 | 0 | 0 | 7168 | 0 | 63.6 | 995.8 |
| 38 | 6718 | 5701 | 319 | 0 | 0 | 6399 | 0 | 17.9 | 823.6 |
| 39 | 5187 | 5176 | 319 | 0 | 0 | 4868 | 0 | 17.6 | 1017.1 |
| 40 | 3982 | 3982 | 433 | 0 | 0 | 3549 | 0 | 11.8 | 1017.3 |
| 41 | 3271 | 3271 | 568 | 0 | 0 | 2703 | 0 | 10.9 | 960.3 |
| 42 | 2756 | 2756 | 704 | 0 | 0 | 2052 | 0 | 6.6 | 1013.1 |
| 43 | 2565 | 2565 | 534 | 0 | 0 | 2031 | 0 | 22.9 | 1010.1 |
| 44 | 1961 | 1961 | 743 | 0 | 0 | 1218 | 0 | 24.2 | 1007.2 |
| 45 | 1440 | 1440 | 831 | 0 | 0 | 609 | 0 | 36.7 | 884.0 |
| 46 | 1212 | 1212 | 874 | 0 | 0 | 338 | 0 | 109.5 | 692.4 |
| 47 | 871 | 871 | 850 | 0 | 0 | 21 | 0 | 132.0 | 491.6 |
| 48 | 388 | 388 | 388 | 0 | 0 | 0 | 0 | 94.5 | 367.1 |
| 49 | 164 | 164 | 164 | 0 | 0 | 0 | 0 | 5.2 | 136.4 |
| 50 | 30 | 30 | 30 | 0 | 0 | 0 | 0 | 11.2 | 113.0 |
| 51 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 10.8 | 10.8 |

⚡ = fault active (t=5.0–15.0 s)
