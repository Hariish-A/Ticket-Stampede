# Run `sweep-tf1-1500`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 2 processes · 100 tickets · 30000 requests (burst 0 at t=0, then 1500.0/s) · seed 1 · 2026-09-24T18:15:00+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 29909 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1060 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 30000 responses in 20.016 s → **1498.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.1 | 6.6 | 159.5 | 321.7 |
| service time (from actual send) | 2.5 | 5.7 | 154.8 | 320.3 |
| client send lag | 0.6 | 1.1 | 3.4 | 35.4 |
| ↳ seller: waiting for a DB connection | 0.1 | 0.1 | 0.2 | 250.7 |
| ↳ seller: allocator queries | 0.5 | 1.2 | 6.2 | 157.3 |
| ↳ seller: whole handler | 1.1 | 3.0 | 40.7 | 312.0 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.4 | 2.7 | 53.5 | 256.2 |

Responses by HTTP status: `{'200': 100, '409': 29899, '502': 1}`  
Requests by kind: `{'fresh': 30000}`  
Transport errors: `{'JSONDecodeError': 1}`  
First sold-out answer at t = 0.299 s  
Seller counters during the run (GET /metrics): `{'claims': 24, 'sold_out_fast': 10055, 'blocking_fallbacks': 5, 'sold_out_checks': 5}`  
Client health: 2 worker processes, CPU per worker `['49%', '49%']` of one core; send lag p99 3.4 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

30000 buyers (user, request_id): final answers `{'purchased': 100, 'sold_out': 29899, 'still_unknown': 1}`. 1 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'502': 1, 'purchased': 100, 'sold_out': 29899}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 1499 | 0 | 100 | 1398 | 0 | 0 | 0 | 4.7 | 300.1 |
| 1 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.0 | 35.4 |
| 2 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.0 | 27.5 |
| 3 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.6 | 5.1 |
| 4 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.5 | 12.1 |
| 5 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.9 | 9.0 |
| 6 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.2 | 9.2 |
| 7 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.2 | 12.0 |
| 8 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.8 | 5.7 |
| 9 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 4.2 | 16.4 |
| 10 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.9 | 8.4 |
| 11 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.2 | 13.0 |
| 12 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.9 | 14.8 |
| 13 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.7 | 6.2 |
| 14 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 5.1 | 92.6 |
| 15 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 17.8 |
| 16 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.9 | 7.1 |
| 17 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 2.8 | 6.0 |
| 18 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.3 | 14.6 |
| 19 | 1500 | 0 | 0 | 1500 | 0 | 0 | 0 | 3.0 | 8.0 |
| 20 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 17.7 | 17.7 |
