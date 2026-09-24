# Run `sweep-tf1-1000`

target `http://lb:8080` · allocator **skiplocked** · open-loop, 8 processes · 100 tickets · 15000 requests (burst 0 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T18:10:17+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 refused otherwise (e.g. 409), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 14910 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 1052 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 15000 responses in 15.003 s → **999.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.3 | 5.1 | 17.9 | 69.6 |
| service time (from actual send) | 2.5 | 4.2 | 15.8 | 67.9 |
| client send lag | 0.8 | 1.2 | 1.7 | 16.1 |
| ↳ seller: waiting for a DB connection | 0.1 | 0.1 | 0.2 | 42.6 |
| ↳ seller: allocator queries | 0.5 | 0.9 | 4.6 | 42.0 |
| ↳ seller: whole handler | 1.0 | 1.9 | 9.1 | 61.6 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.5 | 2.3 | 7.4 | 31.8 |

Responses by HTTP status: `{'200': 100, '409': 14900}`  
Requests by kind: `{'fresh': 15000}`  
First sold-out answer at t = 0.112 s  
Seller counters during the run (GET /metrics): `{'claims': 62, 'blocking_fallbacks': -1, 'sold_out_checks': -1, 'sold_out_fast': 4934}`  
Client health: 8 worker processes, CPU per worker `['12%', '12%', '12%', '12%', '12%', '12%', '12%', '12%']` of one core; send lag p99 1.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

15000 buyers (user, request_id): final answers `{'purchased': 100, 'sold_out': 14900}`. 0 got at least one unclear answer (503 or no response); **0 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 0 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'purchased': 100, 'sold_out': 14900}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 999 | 0 | 100 | 899 | 0 | 0 | 0 | 3.1 | 44.8 |
| 1 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.2 | 5.6 |
| 2 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.5 | 23.1 |
| 3 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 2.9 | 4.9 |
| 4 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.2 | 5.9 |
| 5 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 2.8 | 4.6 |
| 6 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 2.8 | 6.4 |
| 7 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 4.3 | 12.3 |
| 8 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 2.8 | 5.2 |
| 9 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.2 | 13.6 |
| 10 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 4.4 | 34.5 |
| 11 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.2 | 8.9 |
| 12 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.2 | 5.5 |
| 13 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.9 | 13.9 |
| 14 | 1000 | 0 | 0 | 1000 | 0 | 0 | 0 | 3.9 | 21.5 |
| 15 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 5.3 | 5.3 |
