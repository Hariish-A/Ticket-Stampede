[buyer] phase 1: 35000 requests, open-loop, 4 processes -> http://seller1:8000
[buyer] phase 2: 90 probes aimed at actual winners/losers
# Run `profile-1400`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 35000 requests (burst 0 at t=0, then 1400.0/s) · seed 1 · 2026-09-24T09:32:06+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 34910 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 550 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 35000 responses in 25.006 s → **1399.7 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.2 | 3.6 | 401.0 | 718.2 |
| service time (from actual send) | 1.4 | 2.8 | 400.0 | 717.1 |
| client send lag | 0.7 | 1.1 | 1.2 | 21.8 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 13.2 | 219.3 |
| ↳ seller: allocator queries | 0.4 | 0.7 | 4.6 | 146.0 |
| ↳ seller: whole handler | 0.8 | 1.7 | 28.3 | 313.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 0.6 | 1.2 | 392.2 | 709.4 |

Responses by HTTP status: `{'200': 100, '409': 34900}`  
Requests by kind: `{'fresh': 35000}`  
First sold-out answer at t = 0.398 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 10, 'sold_out_checks': 10, 'sold_out_fast': 34900}`  
Client health: 4 worker processes, CPU per worker `['15%', '15%', '15%', '15%']` of one core; send lag p99 1.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

[buyer] report written to results/20260924T093206Z-profile-1400
