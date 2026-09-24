# Run `naive-seed1`

target `http://seller1:8000` · allocator **naive** · 100 tickets · 51090 requests (burst 1000 at t=0, then 1000/s) · seed 1 · 2026-09-24T07:04:36+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 2012 holders > total=100; buyers were confirmed 2010 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1912 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 12 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 2012 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 12 users hold more than one ticket |
| U2 | request_id reused by another user is rejected (422) | **FAIL** | 20/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 41701 sold-out answers, 2012/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 2 |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 61, "users": ["u005426", "u005456", "u005491", "u005513", "u005517", "u005525", "u005541", "u005547", "u005556", "u005572", "u005577", "u005612", "u005620", "u005664", "u005679", "u005746", "u005750", "u005771", "u006550", "u006578"]}, {"ticket_no": 75, "users": ["u006312", "u006391", "u006404", "u006422", "u006530", "u006577", "u006579", "u006618", "u006621", "u006636", "u006716", "u006756", "u006778", "u006970", "u007134", "u007509", "u007618", "u007744", "u007746", "u007891", "u007893"]}, {"ticket_no": 95, "users": ["u006958", "u007226", "u008192", "u008380", "u008402", "u008491", "u008558", "u008560", "u008591", "u008621", "u008634", "u008639", "u008691", "u008709", "u008710", "u008712", "u008717", "u008719", "u008725", "u008728", "u009585"]}]`
- I3: `[{"request_id": "r001408", "tickets": [11, 15]}, {"request_id": "r001409", "tickets": [12, 13]}, {"request_id": "r002004", "tickets": [14, 16]}]`
- U1: `[{"user_id": "u001408", "tickets": [11, 15]}, {"user_id": "u005357", "tickets": [39, 58]}, {"user_id": "u001409", "tickets": [12, 13]}]`
- U2: `[{"request_id": "r000203", "user_id": "xu000203", "status": 409, "ticket_no": null}, {"request_id": "r000116", "user_id": "xu000116", "status": 409, "ticket_no": null}, {"request_id": "r000275", "user_id": "xu000275", "status": 409, "ticket_no": null}]`

## Throughput and latency

51090 responses in 49.642 s → **1029.2 req/s** handled; 0 without a response.

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1.7 | 1005.6 | 1594.9 | 1860.0 |
| service time (from actual send) | 1.2 | 1003.9 | 1527.9 | 1771.1 |
| client send lag | 0.4 | 1.1 | 98.2 | 310.5 |

Responses by HTTP status: `{'200': 2012, '409': 41701, '503': 7377}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000, 'replay_after_sellout': 50, 'rid_conflict': 20, 'same_user_new_rid': 20}`  
First sold-out answer at t = 8.469 s
