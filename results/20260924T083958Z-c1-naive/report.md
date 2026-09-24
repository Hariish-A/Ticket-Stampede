# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · open-loop, 4 processes · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T08:39:58+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 2065 holders > total=100; buyers were confirmed 2062 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1965 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 4 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 2065 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 4 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is rejected (422) | **FAIL** | 20/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 40894 sold-out answers, 2065/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 206 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 63 requests from ticket holders were answered 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **FAIL** | 1312 violations in 348 snapshots: {'count_mismatch': 328, 'oversell': 328, 'duplicate_ticket': 328, 'user_holds_two': 328} |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 61, "users": ["u005062", "u005130", "u005168", "u005185", "u005195", "u005412", "u005428", "u005461", "u005623", "u006113", "u006249", "u006314", "u006606", "u006607", "u006608", "u006609", "u006610", "u006611", "u006612", "u006613", "u006614", "u006623"]}, {"ticket_no": 23, "users": ["u001436", "u002007", "u002041", "u002070", "u002073", "u002165", "u002179", "u002184", "u002234", "u002235", "u002237", "u002334", "u002457", "u002531", "u002548", "u002584", "u002607", "u002628", "u002663", "u002784", "u002810", "u002841", "u002881", "u002884", "u002911", "u004026"]}, {"ticket_no": 41, "users": ["u003558", "u003568", "u003577", "u004272"]}]`
- I3: `[{"request_id": "r006615", "tickets": [71, 72]}, {"request_id": "r004390", "tickets": [49, 63]}, {"request_id": "r006489", "tickets": [69, 70]}]`
- U1: `[{"user_id": "u006615", "tickets": [71, 72]}, {"user_id": "u004811", "tickets": [55, 63]}, {"user_id": "u004390", "tickets": [49, 63]}]`
- U2: `[{"request_id": "r008034", "user_id": "xu008034", "status": 409, "ticket_no": null}, {"request_id": "r003935", "user_id": "xu003935", "status": 409, "ticket_no": null}, {"request_id": "r008292", "user_id": "xu008292", "status": 409, "ticket_no": null}]`
- U5: `[{"user_id": "u009084", "request_id": "r009084", "kind": "dup_sequential"}, {"user_id": "u011116", "request_id": "r011116", "kind": "dup_sequential"}, {"user_id": "u010209", "request_id": "r010209", "kind": "dup_sequential"}]`
- A3: `[{"kind": "count_mismatch", "t_s": 12.057, "sold": 98, "holders": 2021}, {"kind": "oversell", "t_s": 12.057, "sold": 98, "holders": 2021, "total": 100}, {"kind": "duplicate_ticket", "t_s": 12.057, "repeated": 1921}]`

## Throughput and latency

Stampede: 51000 responses in 49.637 s → **1027.5 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 2.3 | 1003.4 | 1508.6 | 2085.2 |
| service time (from actual send) | 1.4 | 1002.6 | 1500.6 | 2072.3 |
| client send lag | 0.7 | 1.1 | 11.7 | 89.1 |

Responses by HTTP status: `{'200': 2065, '409': 40804, '503': 8131}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 8.847 s  
Client health: 4 worker processes, CPU per worker `['12%', '12%', '12%', '12%']` of one core; send lag p99 11.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.
