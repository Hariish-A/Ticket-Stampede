# Run `c2-large-serializable`

target `http://seller1:8000` · allocator **serializable** · open-loop, 4 processes · 5000 tickets · 21000 requests (burst 2000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T08:49:54+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 1472 confirmed, 1472 in /status, total 5000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 1050 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=1472 = 1472 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is rejected (422) | **PASS** | 20 conflicting requests, all rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 0 sold-out answers, 1472/5000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 331 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 190 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 26 snapshots over 21.6s, 0 violations (16 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 21000 responses in 19.232 s → **1091.9 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1006.0 | 1576.8 | 2838.9 | 3559.2 |
| service time (from actual send) | 1005.3 | 1560.6 | 2838.3 | 3558.6 |
| client send lag | 0.7 | 10.1 | 33.8 | 186.1 |

Responses by HTTP status: `{'200': 1467, '503': 19533}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 20000}`  
First sold-out answer at t = None s  
Seller counters during the run (GET /metrics): `{'claims': 1472, 'serialization_retries': 24927, 'serialization_gave_up': 241, 'unique_violation_retries': 2}`  
Client health: 4 worker processes, CPU per worker `['15%', '15%', '15%', '15%']` of one core; send lag p99 33.8 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
