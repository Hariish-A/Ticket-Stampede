# Run `c1-naive`

target `http://seller1:8000` · allocator **naive** · 100 tickets · 51000 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T07:39:18+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 1659 holders > total=100; buyers were confirmed 1656 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1559 repeated ticket numbers; 93 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 4 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 1659 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 4 users hold more than one ticket |
| U2 | A winner's request_id reused by another user is rejected (422) | **FAIL** | 20/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 43556 sold-out answers, 1659/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 173 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **FAIL** | 64 requests from ticket holders were answered 'sold out' |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 83, "users": ["u005397", "u005402", "u005434", "u005441", "u005449", "u005476", "u005477", "u005479", "u005480", "u005481", "u005482", "u005483", "u005484", "u005514", "u005515", "u005517", "u005520", "u005594", "u005707", "u006458", "u006514"]}, {"ticket_no": 9, "users": ["u000160", "u000161", "u000162", "u000163", "u000164", "u000273", "u000275", "u000276", "u000277", "u000499", "u000500", "u000501", "u000838", "u000839", "u000840", "u000844", "u002151", "u002154"]}, {"ticket_no": 32, "users": ["u002329", "u002330", "u002388", "u002421", "u002429", "u002451", "u002474", "u002475", "u002476", "u002480", "u002523", "u002547", "u002588", "u002714", "u003555"]}]`
- I3: `[{"request_id": "r000253", "tickets": [2, 21]}, {"request_id": "r001335", "tickets": [16, 20]}, {"request_id": "r002011", "tickets": [6, 18]}]`
- U1: `[{"user_id": "u000253", "tickets": [2, 21]}, {"user_id": "u004617", "tickets": [63, 67]}, {"user_id": "u001335", "tickets": [16, 20]}]`
- U2: `[{"request_id": "r004871", "user_id": "xu004871", "status": 409, "ticket_no": null}, {"request_id": "r003133", "user_id": "xu003133", "status": 409, "ticket_no": null}, {"request_id": "r004935", "user_id": "xu004935", "status": 409, "ticket_no": null}]`
- U5: `[{"user_id": "u006972", "request_id": "r006972", "kind": "fresh"}, {"user_id": "u007087", "request_id": "r007087", "kind": "dup_sequential"}, {"user_id": "u007737", "request_id": "r007737", "kind": "fresh"}]`

## Throughput and latency

Stampede: 51000 responses in 49.651 s → **1027.2 req/s** handled; 0 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1.6 | 1002.1 | 1520.4 | 1779.0 |
| service time (from actual send) | 1.2 | 1001.4 | 1458.4 | 1639.9 |
| client send lag | 0.4 | 1.1 | 74.2 | 238.8 |

Responses by HTTP status: `{'200': 1659, '409': 43466, '503': 5875}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000}`  
First sold-out answer at t = 6.465 s
