# Run `sweep-tf1-4000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 60000 requests (burst 0 at t=0, then 4000.0/s) · seed 1 · 2026-09-24T18:11:27+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 0 refused otherwise (e.g. 409), 20 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 28730 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1055 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 59679 responses in 17.081 s → **3493.9 req/s** handled; 321 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 973.9 | 9806.5 | 10143.1 | 10314.3 |
| service time (from actual send) | 943.0 | 9802.0 | 10131.4 | 10279.9 |
| client send lag | 1.0 | 56.9 | 294.7 | 433.2 |
| ↳ seller: waiting for a DB connection | 0.1 | 861.0 | 994.5 | 1005.2 |
| ↳ seller: allocator queries | 4.8 | 17.1 | 49.9 | 282.0 |
| ↳ seller: whole handler | 186.1 | 1035.9 | 1149.4 | 1281.8 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 67.7 | 9863.6 | 10134.7 | 10253.8 |

Responses by HTTP status: `{'0': 321, '200': 100, '409': 28730, '502': 19310, '503': 11539}`  
Requests by kind: `{'fresh': 60000}`  
Transport errors: `{'TimeoutError': 321, 'JSONDecodeError': 19310}`  
First sold-out answer at t = 0.203 s  
Seller counters during the run (GET /metrics): `{'claims': 30, 'blocking_fallbacks': 8, 'sold_out_fast': 9654, 'sold_out_checks': 8}`  
Client health: 8 worker processes, CPU per worker `['54%', '53%', '55%', '55%', '56%', '56%', '55%', '55%']` of one core; send lag p99 294.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

60000 buyers (user, request_id): final answers `{'sold_out': 28730, 'purchased': 100, 'turned_away_known': 11539, 'still_unknown': 19631}`. 31170 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 19310, 'no_response': 321, 'not_attempted': 11539, 'purchased': 100, 'sold_out': 28730}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3999 | 0 | 100 | 3818 | 0 | 81 | 0 | 732.5 | 5397.9 |
| 1 | 4000 | 0 | 0 | 3722 | 0 | 203 | 75 | 8012.4 | 10249.8 |
| 2 | 4000 | 0 | 0 | 3487 | 0 | 351 | 162 | 1015.7 | 10198.0 |
| 3 | 4000 | 0 | 0 | 2877 | 0 | 1039 | 84 | 1033.8 | 10050.4 |
| 4 | 4000 | 0 | 0 | 2958 | 0 | 1042 | 0 | 9735.5 | 9891.6 |
| 5 | 4000 | 0 | 0 | 2702 | 0 | 1298 | 0 | 1033.3 | 9914.2 |
| 6 | 4000 | 0 | 0 | 1930 | 0 | 2070 | 0 | 1081.3 | 9313.1 |
| 7 | 4000 | 0 | 0 | 1941 | 0 | 2059 | 0 | 1304.6 | 8832.8 |
| 8 | 4000 | 0 | 0 | 1884 | 0 | 2076 | 0 | 1290.9 | 8321.5 |
| 9 | 4000 | 0 | 0 | 2309 | 0 | 1048 | 0 | 1089.7 | 7730.5 |
| 10 | 4000 | 0 | 0 | 1102 | 0 | 272 | 0 | 100.8 | 6657.3 |
| 11 | 4000 | 0 | 0 | 0 | 0 | 0 | 0 | 1.9 | 18.6 |
| 12 | 4000 | 0 | 0 | 0 | 0 | 0 | 0 | 1.7 | 28.0 |
| 13 | 4000 | 0 | 0 | 0 | 0 | 0 | 0 | 1.8 | 8.2 |
| 14 | 4000 | 0 | 0 | 0 | 0 | 0 | 0 | 1.6 | 5.6 |
| 15 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 49.8 | 49.8 |
