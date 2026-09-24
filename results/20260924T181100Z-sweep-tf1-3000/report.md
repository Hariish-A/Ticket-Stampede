# Run `sweep-tf1-3000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 45000 requests (burst 0 at t=0, then 3000.0/s) · seed 1 · 2026-09-24T18:11:00+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 21361 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1054 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 39724 responses in 18.458 s → **2152.2 req/s** handled; 5276 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1047.3 | 4680.7 | 10029.5 | 10650.4 |
| service time (from actual send) | 1045.7 | 4679.8 | 10020.8 | 10637.3 |
| client send lag | 0.9 | 5.5 | 49.2 | 151.3 |
| ↳ seller: waiting for a DB connection | 0.1 | 899.4 | 997.5 | 1028.8 |
| ↳ seller: allocator queries | 9.2 | 27.2 | 80.5 | 253.1 |
| ↳ seller: whole handler | 982.8 | 1067.4 | 1201.9 | 1520.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 37.6 | 4658.5 | 10001.6 | 10479.7 |

Responses by HTTP status: `{'0': 5276, '200': 100, '409': 21351, '503': 18273}`  
Requests by kind: `{'fresh': 45000}`  
Transport errors: `{'TimeoutError': 5276}`  
First sold-out answer at t = 0.141 s  
Seller counters during the run (GET /metrics): `{'claims': 37, 'blocking_fallbacks': 6, 'sold_out_checks': 6, 'sold_out_fast': 8855}`  
Client health: 8 worker processes, CPU per worker `['43%', '43%', '43%', '44%', '43%', '43%', '43%', '44%']` of one core; send lag p99 49.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

45000 buyers (user, request_id): final answers `{'purchased': 100, 'sold_out': 21351, 'turned_away_known': 18273, 'still_unknown': 5276}`. 23549 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'no_response': 5276, 'not_attempted': 18273, 'purchased': 100, 'sold_out': 21351}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2999 | 0 | 100 | 2848 | 0 | 51 | 0 | 237.5 | 3336.9 |
| 1 | 3000 | 0 | 0 | 2441 | 0 | 555 | 4 | 1075.7 | 9869.0 |
| 2 | 3000 | 0 | 0 | 1312 | 0 | 369 | 1319 | 650.7 | 10393.8 |
| 3 | 3000 | 0 | 0 | 1138 | 0 | 816 | 1046 | 743.1 | 1066.6 |
| 4 | 3000 | 0 | 0 | 692 | 0 | 1248 | 1060 | 1054.6 | 1248.9 |
| 5 | 3000 | 0 | 0 | 945 | 0 | 731 | 1324 | 1019.5 | 1193.7 |
| 6 | 3000 | 0 | 0 | 1068 | 0 | 1409 | 523 | 1033.7 | 10175.0 |
| 7 | 3000 | 0 | 0 | 1754 | 0 | 1246 | 0 | 1057.8 | 10119.6 |
| 8 | 3000 | 0 | 0 | 1157 | 0 | 1843 | 0 | 1076.1 | 9439.3 |
| 9 | 3000 | 0 | 0 | 1330 | 0 | 1670 | 0 | 1085.6 | 8611.5 |
| 10 | 3000 | 0 | 0 | 1271 | 0 | 1729 | 0 | 1051.5 | 7485.7 |
| 11 | 3000 | 0 | 0 | 1150 | 0 | 1850 | 0 | 1047.6 | 7120.8 |
| 12 | 3000 | 0 | 0 | 625 | 0 | 2375 | 0 | 1095.3 | 5581.9 |
| 13 | 3000 | 0 | 0 | 997 | 0 | 2003 | 0 | 1135.5 | 4674.1 |
| 14 | 3000 | 0 | 0 | 2622 | 0 | 378 | 0 | 906.9 | 1108.6 |
| 15 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 747.5 | 747.5 |
