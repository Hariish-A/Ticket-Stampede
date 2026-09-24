# Run `sweep-tf1-6000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 90000 requests (burst 0 at t=0, then 6000.0/s) · seed 1 · 2026-09-24T18:12:24+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 0 rejected (422), 0 refused otherwise (e.g. 409), 20 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 18275 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1057 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 86735 responses in 15.79 s → **5493.1 req/s** handled; 3265 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1895.7 | 6876.6 | 11401.1 | 12274.4 |
| service time (from actual send) | 536.1 | 6628.1 | 10553.9 | 11309.4 |
| client send lag | 959.3 | 2072.5 | 2447.5 | 2600.2 |
| ↳ seller: waiting for a DB connection | 0.1 | 775.4 | 965.0 | 1002.8 |
| ↳ seller: allocator queries | 5.5 | 20.1 | 51.8 | 289.0 |
| ↳ seller: whole handler | 50.6 | 1009.3 | 1058.2 | 1185.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 2504.5 | 10091.0 | 10874.4 | 11296.2 |

Responses by HTTP status: `{'0': 3265, '200': 100, '409': 18275, '502': 65583, '503': 2777}`  
Requests by kind: `{'fresh': 90000}`  
Transport errors: `{'JSONDecodeError': 65583, 'TimeoutError': 3265}`  
First sold-out answer at t = 0.318 s  
Seller counters during the run (GET /metrics): `{'claims': 27, 'sold_out_fast': 7386, 'blocking_fallbacks': 20, 'sold_out_checks': 20}`  
Client health: 8 worker processes, CPU per worker `['76%', '79%', '74%', '76%', '74%', '76%', '75%', '76%']` of one core; send lag p99 2447.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

90000 buyers (user, request_id): final answers `{'still_unknown': 68848, 'purchased': 100, 'sold_out': 18275, 'turned_away_known': 2777}`. 71625 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 65583, 'no_response': 3265, 'not_attempted': 2777, 'purchased': 100, 'sold_out': 18275}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 5999 | 0 | 100 | 5500 | 0 | 192 | 0 | 3351.7 | 9421.6 |
| 1 | 6000 | 0 | 0 | 4895 | 0 | 484 | 621 | 8914.1 | 11257.1 |
| 2 | 6000 | 0 | 0 | 2758 | 0 | 847 | 1896 | 3221.9 | 11312.2 |
| 3 | 6000 | 0 | 0 | 3283 | 0 | 929 | 646 | 3369.4 | 12094.4 |
| 4 | 6000 | 0 | 0 | 1770 | 0 | 325 | 102 | 2494.9 | 11486.4 |
| 5 | 6000 | 0 | 0 | 69 | 0 | 0 | 0 | 2117.9 | 3187.4 |
| 6 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 2046.8 | 3541.9 |
| 7 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1892.6 | 3376.3 |
| 8 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1980.0 | 3191.3 |
| 9 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1785.0 | 3357.0 |
| 10 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1633.5 | 2780.8 |
| 11 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1455.8 | 2697.0 |
| 12 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 1018.5 | 2108.5 |
| 13 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 483.9 | 1737.9 |
| 14 | 6000 | 0 | 0 | 0 | 0 | 0 | 0 | 35.9 | 1022.1 |
| 15 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 154.9 | 154.9 |
