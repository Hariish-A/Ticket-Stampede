# Run `d10-hostfwd`

target `http://host.docker.internal:8001` · allocator **skiplocked** · open-loop, 4 processes · 100 tickets · 12000 requests (burst 0 at t=0, then 800.0/s) · seed 1 · 2026-09-24T09:36:31+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 100 confirmed, 100 in /status, total 100 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 50 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=100 = 100 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 11910 sold-out answers, 100/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 556 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 60 repeat requests from holders, none told 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 12000 responses in 15.004 s → **799.8 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 3.1 | 4.0 | 7.5 | 52.5 |
| service time (from actual send) | 2.4 | 3.1 | 6.6 | 50.5 |
| client send lag | 0.7 | 1.1 | 1.2 | 4.0 |
| ↳ seller: waiting for a DB connection | 0.0 | 0.0 | 0.1 | 15.7 |
| ↳ seller: allocator queries | 0.4 | 0.5 | 1.2 | 26.9 |
| ↳ seller: whole handler | 0.7 | 1.0 | 2.7 | 35.2 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 1.7 | 2.1 | 2.9 | 22.3 |

Responses by HTTP status: `{'200': 100, '409': 11900}`  
Requests by kind: `{'fresh': 12000}`  
First sold-out answer at t = 0.133 s  
Seller counters during the run (GET /metrics): `{'claims': 100, 'blocking_fallbacks': 2, 'sold_out_checks': 2, 'sold_out_fast': 11908}`  
Client health: 4 worker processes, CPU per worker `['12%', '12%', '12%', '12%']` of one core; send lag p99 1.2 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
