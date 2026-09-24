# Run `slowdb-failfast`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 233485 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T10:27:26+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 14971 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 193561 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 3270 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 759 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 41979 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 171 snapshots over 55.0s, 0 violations (9 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 29 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 232513 responses in 51.385 s → **4525.0 req/s** handled; 972 without a response. Then 116 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 14.6 | 98.4 | 942.5 | 10566.1 |
| service time (from actual send) | 14.4 | 96.9 | 936.5 | 10566.1 |
| client send lag | 0.0 | 0.7 | 7.0 | 184.1 |
| ↳ seller: waiting for a DB connection | 47.8 | 202.6 | 396.9 | 998.6 |
| ↳ seller: allocator queries | 14.2 | 48.9 | 134.3 | 483.5 |
| ↳ seller: whole handler | 88.9 | 307.8 | 1007.2 | 3155.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 7.5 | 42.0 | 136.6 | 1658.6 |

Responses by HTTP status: `{'0': 972, '200': 15227, '409': 3261, '503': 214025}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 192485}`  
Transport errors: `{'TimeoutError': 972}`  
First sold-out answer at t = 44.311 s  
Seller counters during the run (GET /metrics): `{'claims': 14992, 'unique_violation_retries': 9, 'blocking_fallbacks': 6, 'sold_out_fast': 3264, 'sold_out_checks': 6, 'admission_shed': 214395}`  
Client health: 4 worker processes, CPU per worker `['41%', '42%', '42%', '41%']` of one core; send lag p99 7.0 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 14971, 'turned_away_known': 20958, 'still_unknown': 859, 'sold_out': 3212}`. 36797 got at least one unclear answer (503 or no response); **38 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 11705 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'no_response': 972, 'not_attempted': 214007, 'purchased': 15227, 'sold_out': 3261, 'unknown': 18}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3079 | 1036 | 710 | 0 | 0 | 2369 | 0 | 63.1 | 1598.4 |
| 1 | 2885 | 1855 | 802 | 0 | 0 | 2083 | 0 | 6.6 | 181.3 |
| 2 | 2807 | 1790 | 1095 | 0 | 0 | 1712 | 0 | 7.5 | 150.1 |
| 3 | 2566 | 1539 | 1113 | 0 | 0 | 1453 | 0 | 12.2 | 159.2 |
| 4 | 2245 | 1224 | 984 | 0 | 17 | 1244 | 0 | 17.9 | 1027.3 |
| 5 ⚡ | 2592 | 1563 | 0 | 0 | 1 | 2591 | 0 | 0.6 | 1002.3 |
| 6 ⚡ | 3551 | 2528 | 0 | 0 | 0 | 3551 | 0 | 0.6 | 1001.5 |
| 7 ⚡ | 3991 | 2963 | 0 | 0 | 0 | 3991 | 0 | 0.6 | 1000.3 |
| 8 ⚡ | 4417 | 3400 | 0 | 0 | 0 | 4417 | 0 | 0.6 | 1007.1 |
| 9 ⚡ | 4686 | 3661 | 0 | 0 | 0 | 4686 | 0 | 0.6 | 1003.8 |
| 10 ⚡ | 5055 | 4027 | 0 | 0 | 0 | 5055 | 0 | 0.7 | 1004.4 |
| 11 ⚡ | 5396 | 4382 | 0 | 0 | 0 | 5396 | 0 | 1.0 | 1003.5 |
| 12 ⚡ | 5675 | 4641 | 0 | 0 | 0 | 5675 | 0 | 0.7 | 1002.5 |
| 13 ⚡ | 6052 | 5026 | 0 | 0 | 0 | 6052 | 0 | 0.8 | 1001.4 |
| 14 ⚡ | 6174 | 5159 | 11 | 0 | 0 | 6163 | 0 | 0.7 | 1004.6 |
| 15 ⚡ | 5934 | 4901 | 53 | 0 | 0 | 4909 | 972 | 305.7 | 10104.9 |
| 16 | 5805 | 4778 | 509 | 0 | 0 | 5296 | 0 | 8.9 | 202.9 |
| 17 | 5868 | 4842 | 544 | 0 | 0 | 5324 | 0 | 8.3 | 205.0 |
| 18 | 6020 | 4995 | 341 | 0 | 0 | 5679 | 0 | 17.4 | 310.1 |
| 19 | 6278 | 5244 | 311 | 0 | 0 | 5967 | 0 | 19.6 | 293.6 |
| 20 | 6084 | 5061 | 372 | 0 | 0 | 5712 | 0 | 15.8 | 277.6 |
| 21 | 6050 | 5023 | 258 | 0 | 0 | 5792 | 0 | 27.6 | 384.3 |
| 22 | 6218 | 5199 | 347 | 0 | 0 | 5871 | 0 | 17.1 | 313.5 |
| 23 | 6077 | 5054 | 431 | 0 | 0 | 5646 | 0 | 11.1 | 234.0 |
| 24 | 5992 | 4965 | 341 | 0 | 0 | 5651 | 0 | 18.9 | 313.8 |
| 25 | 6284 | 5263 | 291 | 0 | 0 | 5993 | 0 | 26.4 | 313.6 |
| 26 | 6427 | 5401 | 332 | 0 | 0 | 6095 | 0 | 14.8 | 262.5 |
| 27 | 6463 | 5441 | 341 | 0 | 0 | 6122 | 0 | 16.4 | 307.6 |
| 28 | 6732 | 5706 | 255 | 0 | 0 | 6477 | 0 | 20.7 | 359.5 |
| 29 | 6636 | 5618 | 330 | 0 | 0 | 6306 | 0 | 20.4 | 293.4 |
| 30 | 6404 | 5385 | 297 | 0 | 0 | 6107 | 0 | 22.1 | 266.8 |
| 31 | 6550 | 5526 | 177 | 0 | 0 | 6373 | 0 | 44.4 | 495.9 |
| 32 | 6569 | 5540 | 259 | 0 | 0 | 6310 | 0 | 28.5 | 308.0 |
| 33 | 6485 | 5460 | 306 | 0 | 0 | 6179 | 0 | 38.0 | 364.4 |
| 34 | 6406 | 5368 | 251 | 0 | 0 | 6155 | 0 | 28.8 | 339.1 |
| 35 | 6609 | 5579 | 244 | 0 | 0 | 6365 | 0 | 23.9 | 365.2 |
| 36 | 6410 | 5385 | 312 | 0 | 0 | 6098 | 0 | 27.1 | 336.8 |
| 37 | 6545 | 5517 | 233 | 0 | 0 | 6312 | 0 | 38.3 | 343.7 |
| 38 | 6255 | 5238 | 246 | 0 | 0 | 6009 | 0 | 34.3 | 346.5 |
| 39 | 4725 | 4714 | 421 | 0 | 0 | 4304 | 0 | 18.7 | 256.5 |
| 40 | 3620 | 3620 | 556 | 0 | 0 | 3064 | 0 | 18.7 | 239.8 |
| 41 | 3024 | 3024 | 492 | 0 | 0 | 2532 | 0 | 21.7 | 272.6 |
| 42 | 2492 | 2492 | 759 | 0 | 0 | 1733 | 0 | 21.5 | 274.5 |
| 43 | 2139 | 2139 | 598 | 0 | 0 | 1541 | 0 | 38.6 | 219.5 |
| 44 | 1835 | 1835 | 249 | 663 | 0 | 923 | 0 | 42.0 | 232.9 |
| 45 | 1330 | 1330 | 16 | 802 | 0 | 512 | 0 | 28.7 | 161.5 |
| 46 | 982 | 982 | 13 | 777 | 0 | 192 | 0 | 14.6 | 184.0 |
| 47 | 615 | 615 | 16 | 579 | 0 | 20 | 0 | 11.1 | 132.3 |
| 48 | 307 | 307 | 8 | 299 | 0 | 0 | 0 | 16.4 | 152.5 |
| 49 | 120 | 120 | 2 | 118 | 0 | 0 | 0 | 4.7 | 141.8 |
| 50 | 22 | 22 | 1 | 21 | 0 | 0 | 0 | 4.4 | 89.1 |
| 51 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 80.2 | 80.2 |

⚡ = fault active (t=5.0–15.0 s)
