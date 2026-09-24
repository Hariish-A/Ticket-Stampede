# Run `slowdb-failfast`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 234375 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T10:22:37+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 14987 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 194451 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **FAIL** | 6/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 3172 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 757 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 43340 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 169 snapshots over 54.6s, 0 violations (9 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 13 tickets in /status were never confirmed to their buyer |

Examples of failures:

- U2: `[{"request_id": "r037029", "user_id": "xu037029", "status": 503, "ticket_no": null}, {"request_id": "r003318", "user_id": "xu003318", "status": 503, "ticket_no": null}, {"request_id": "r030739", "user_id": "xu030739", "status": 503, "ticket_no": null}]`

## Throughput and latency

Stampede: 234375 responses in 51.123 s → **4584.6 req/s** handled; 0 without a response. Then 116 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 14.3 | 82.9 | 454.3 | 7053.4 |
| service time (from actual send) | 14.2 | 81.5 | 453.8 | 7053.4 |
| client send lag | 0.0 | 0.7 | 5.6 | 199.4 |
| ↳ seller: waiting for a DB connection | 45.3 | 198.3 | 389.4 | 987.2 |
| ↳ seller: allocator queries | 14.4 | 48.8 | 117.2 | 432.6 |
| ↳ seller: whole handler | 87.3 | 305.9 | 1011.6 | 3143.7 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 7.2 | 42.7 | 132.0 | 1738.1 |

Responses by HTTP status: `{'200': 15265, '409': 3164, '503': 215946}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 193375}`  
First sold-out answer at t = 44.328 s  
Seller counters during the run (GET /metrics): `{'claims': 14987, 'unique_violation_retries': 8, 'blocking_fallbacks': 11, 'sold_out_checks': 11, 'sold_out_fast': 3161, 'admission_shed': 215358}`  
Client health: 4 worker processes, CPU per worker `['42%', '41%', '41%', '42%']` of one core; send lag p99 5.6 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 14987, 'still_unknown': 21879, 'sold_out': 3134}`. 37028 got at least one unclear answer (503 or no response); **28 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 11967 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'not_attempted': 215928, 'purchased': 15265, 'sold_out': 3164, 'unknown': 18}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3093 | 1050 | 526 | 0 | 0 | 2567 | 0 | 66.9 | 1733.0 |
| 1 | 3100 | 2070 | 784 | 0 | 0 | 2316 | 0 | 6.6 | 197.4 |
| 2 | 2928 | 1911 | 1130 | 0 | 0 | 1798 | 0 | 7.2 | 133.3 |
| 3 | 2707 | 1680 | 1058 | 0 | 0 | 1649 | 0 | 6.5 | 200.3 |
| 4 | 2387 | 1366 | 1016 | 0 | 16 | 1355 | 0 | 17.4 | 1003.2 |
| 5 ⚡ | 2688 | 1659 | 0 | 0 | 2 | 2686 | 0 | 0.6 | 1000.9 |
| 6 ⚡ | 3602 | 2579 | 0 | 0 | 0 | 3602 | 0 | 0.6 | 1000.4 |
| 7 ⚡ | 4034 | 3006 | 0 | 0 | 0 | 4034 | 0 | 0.6 | 1003.3 |
| 8 ⚡ | 4542 | 3525 | 0 | 0 | 0 | 4542 | 0 | 0.8 | 1011.5 |
| 9 ⚡ | 4726 | 3701 | 0 | 0 | 0 | 4726 | 0 | 0.6 | 1011.8 |
| 10 ⚡ | 5067 | 4039 | 0 | 0 | 0 | 5067 | 0 | 0.7 | 1018.0 |
| 11 ⚡ | 5464 | 4450 | 0 | 0 | 0 | 5464 | 0 | 0.9 | 1001.9 |
| 12 ⚡ | 5765 | 4731 | 0 | 0 | 0 | 5765 | 0 | 0.7 | 1002.5 |
| 13 ⚡ | 5987 | 4961 | 0 | 0 | 0 | 5987 | 0 | 0.9 | 1001.7 |
| 14 ⚡ | 6285 | 5270 | 7 | 0 | 0 | 6278 | 0 | 0.8 | 1020.3 |
| 15 ⚡ | 6336 | 5303 | 48 | 0 | 0 | 6288 | 0 | 147.0 | 6562.3 |
| 16 | 6329 | 5302 | 402 | 0 | 0 | 5927 | 0 | 11.7 | 236.5 |
| 17 | 6510 | 5484 | 390 | 0 | 0 | 6120 | 0 | 13.1 | 230.9 |
| 18 | 6690 | 5665 | 412 | 0 | 0 | 6278 | 0 | 11.7 | 219.0 |
| 19 | 6787 | 5753 | 266 | 0 | 0 | 6521 | 0 | 25.6 | 340.5 |
| 20 | 6455 | 5432 | 260 | 0 | 0 | 6195 | 0 | 20.8 | 351.1 |
| 21 | 6593 | 5566 | 230 | 0 | 0 | 6363 | 0 | 27.8 | 341.9 |
| 22 | 6564 | 5545 | 363 | 0 | 0 | 6201 | 0 | 14.7 | 252.5 |
| 23 | 6540 | 5517 | 322 | 0 | 0 | 6218 | 0 | 19.1 | 293.7 |
| 24 | 6350 | 5323 | 339 | 0 | 0 | 6011 | 0 | 18.6 | 294.7 |
| 25 | 6387 | 5366 | 386 | 0 | 0 | 6001 | 0 | 12.6 | 303.0 |
| 26 | 6278 | 5252 | 394 | 0 | 0 | 5884 | 0 | 16.2 | 264.0 |
| 27 | 6247 | 5225 | 302 | 0 | 0 | 5945 | 0 | 18.7 | 273.6 |
| 28 | 6376 | 5350 | 329 | 0 | 0 | 6047 | 0 | 18.8 | 307.3 |
| 29 | 6130 | 5112 | 279 | 0 | 0 | 5851 | 0 | 31.6 | 326.9 |
| 30 | 6216 | 5197 | 356 | 0 | 0 | 5860 | 0 | 17.9 | 304.3 |
| 31 | 6233 | 5209 | 208 | 0 | 0 | 6025 | 0 | 29.7 | 366.0 |
| 32 | 6206 | 5177 | 329 | 0 | 0 | 5877 | 0 | 15.8 | 295.4 |
| 33 | 5976 | 4951 | 355 | 0 | 0 | 5621 | 0 | 21.0 | 370.2 |
| 34 | 6398 | 5360 | 252 | 0 | 0 | 6146 | 0 | 34.4 | 317.1 |
| 35 | 6242 | 5212 | 357 | 0 | 0 | 5885 | 0 | 16.4 | 299.6 |
| 36 | 6104 | 5079 | 319 | 0 | 0 | 5785 | 0 | 22.2 | 330.1 |
| 37 | 6076 | 5048 | 359 | 0 | 0 | 5717 | 0 | 17.4 | 298.3 |
| 38 | 6170 | 5153 | 197 | 0 | 0 | 5973 | 0 | 41.1 | 474.8 |
| 39 | 4520 | 4509 | 524 | 0 | 0 | 3996 | 0 | 23.8 | 248.3 |
| 40 | 3420 | 3420 | 681 | 0 | 0 | 2739 | 0 | 17.1 | 278.7 |
| 41 | 2936 | 2936 | 367 | 0 | 0 | 2569 | 0 | 29.6 | 413.1 |
| 42 | 2259 | 2259 | 809 | 0 | 0 | 1450 | 0 | 24.5 | 228.7 |
| 43 | 2032 | 2032 | 670 | 0 | 0 | 1362 | 0 | 40.5 | 250.6 |
| 44 | 1690 | 1690 | 165 | 752 | 0 | 773 | 0 | 32.8 | 231.6 |
| 45 | 1222 | 1222 | 35 | 873 | 0 | 314 | 0 | 14.9 | 144.9 |
| 46 | 880 | 880 | 18 | 751 | 0 | 111 | 0 | 9.7 | 142.0 |
| 47 | 529 | 529 | 14 | 476 | 0 | 39 | 0 | 12.5 | 130.2 |
| 48 | 203 | 203 | 5 | 198 | 0 | 0 | 0 | 4.1 | 118.2 |
| 49 | 88 | 88 | 0 | 88 | 0 | 0 | 0 | 3.0 | 95.3 |
| 50 | 26 | 26 | 2 | 24 | 0 | 0 | 0 | 4.1 | 154.1 |
| 51 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 70.0 | 70.0 |

⚡ = fault active (t=5.0–15.0 s)
