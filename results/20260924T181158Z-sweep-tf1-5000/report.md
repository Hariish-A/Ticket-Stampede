# Run `sweep-tf1-5000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 75000 requests (burst 0 at t=0, then 5000.0/s) · seed 1 · 2026-09-24T18:11:58+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 0 refused otherwise (e.g. 409), 20 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 22712 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1056 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 73671 responses in 15.66 s → **4704.3 req/s** handled; 1329 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 326.2 | 8706.1 | 10515.3 | 10959.6 |
| service time (from actual send) | 142.1 | 8702.3 | 10475.5 | 10923.9 |
| client send lag | 4.3 | 516.2 | 922.9 | 1049.8 |
| ↳ seller: waiting for a DB connection | 0.1 | 840.4 | 995.0 | 1007.6 |
| ↳ seller: allocator queries | 5.0 | 16.9 | 40.2 | 143.2 |
| ↳ seller: whole handler | 43.9 | 1018.8 | 1059.7 | 1153.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 490.3 | 9769.4 | 10598.2 | 10914.0 |

Responses by HTTP status: `{'0': 1329, '200': 100, '409': 22712, '502': 46088, '503': 4771}`  
Requests by kind: `{'fresh': 75000}`  
Transport errors: `{'JSONDecodeError': 46088, 'TimeoutError': 1329}`  
First sold-out answer at t = 0.166 s  
Seller counters during the run (GET /metrics): `{'claims': 40, 'sold_out_fast': 8134}`  
Client health: 8 worker processes, CPU per worker `['68%', '66%', '66%', '69%', '67%', '67%', '68%', '68%']` of one core; send lag p99 922.9 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

75000 buyers (user, request_id): final answers `{'still_unknown': 47417, 'purchased': 100, 'sold_out': 22712, 'turned_away_known': 4771}`. 52188 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 46088, 'no_response': 1329, 'not_attempted': 4771, 'purchased': 100, 'sold_out': 22712}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 4999 | 0 | 100 | 4381 | 0 | 120 | 0 | 1272.5 | 7780.5 |
| 1 | 5000 | 0 | 0 | 4828 | 0 | 172 | 0 | 7874.8 | 8959.8 |
| 2 | 5000 | 0 | 0 | 4413 | 0 | 587 | 0 | 9011.0 | 9622.7 |
| 3 | 5000 | 0 | 0 | 3931 | 0 | 1017 | 52 | 9609.2 | 10366.1 |
| 4 | 5000 | 0 | 0 | 2661 | 0 | 1130 | 1192 | 1379.6 | 10763.7 |
| 5 | 5000 | 0 | 0 | 1887 | 0 | 1351 | 85 | 1570.4 | 10237.9 |
| 6 | 5000 | 0 | 0 | 611 | 0 | 394 | 0 | 1060.0 | 2216.8 |
| 7 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 827.1 | 1317.1 |
| 8 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 531.0 | 1181.6 |
| 9 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 13.8 | 649.3 |
| 10 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 2.6 | 43.6 |
| 11 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 3.1 | 99.3 |
| 12 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 1.7 | 24.8 |
| 13 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 2.1 | 56.7 |
| 14 | 5000 | 0 | 0 | 0 | 0 | 0 | 0 | 2.7 | 68.5 |
| 15 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 46.9 | 46.9 |
