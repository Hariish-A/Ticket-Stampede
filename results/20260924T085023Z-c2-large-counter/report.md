# Run `c2-large-counter`

target `http://seller1:8000` · allocator **counter** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T08:50:23+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 4704 confirmed, 4704 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=4704 = 4704 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 4704/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 332 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 395 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 27 snapshots over 21.4s, 0 violations (14 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 19.104 s → **1099.3 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1007.2 | 1504.1 | 2355.1 | 2627.4 |
| service time (from actual send) | 1006.5 | 1482.2 | 2353.7 | 2626.2 |
| client send lag | 0.7 | 9.4 | 31.5 | 173.1 |

Responses by HTTP status: `{'200': 4740, '503': 16260}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 4704, 'unique_violation_retries': 22}`  
Client health: 4 worker processes, CPU per worker `['15%', '15%', '15%', '15%']` of one core; send lag p99 31.5 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
