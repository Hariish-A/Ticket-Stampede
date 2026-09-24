# Run `naive-seed3`

target `http://seller1:8000` · allocator **naive** · 100 tickets · 51090 requests (burst 1000 at t=0, then 1000/s) · seed 3 · 2026-09-24T07:06:40+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 1972 holders > total=100; buyers were confirmed 1970 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1872 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 6 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 1972 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 6 users hold more than one ticket |
| U2 | request_id reused by another user is rejected (422) | **FAIL** | 20/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 41180 sold-out answers, 1972/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 4 |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 19, "users": ["u001328", "u001447", "u002331", "u002400", "u002567", "u002744", "u002813", "u002857", "u002955", "u003100", "u003310", "u003767"]}, {"ticket_no": 40, "users": ["u003282", "u003495", "u003566", "u003717", "u003718", "u003722", "u003783", "u003789", "u003794", "u003838", "u003916", "u003975", "u004378", "u004403", "u004445", "u004493", "u004499", "u004505", "u004517", "u004544", "u004551", "u004555", "u004617", "u004633", "u004642", "u004675", "u004773", "u004807", "u004899", "u005472", "u005575"]}, {"ticket_no": 64, "users": ["u005987", "u006369", "u006422", "u006442", "u006444", "u006472", "u006513", "u006535", "u006617", "u006647", "u006706", "u007562", "u007617", "u007636"]}]`
- I3: `[{"request_id": "r001318", "tickets": [2, 12]}, {"request_id": "r002032", "tickets": [14, 17]}, {"request_id": "r005044", "tickets": [47, 50]}]`
- U1: `[{"user_id": "u001318", "tickets": [2, 12]}, {"user_id": "u005044", "tickets": [47, 50]}, {"user_id": "u002032", "tickets": [14, 17]}]`
- U2: `[{"request_id": "r000113", "user_id": "xu000113", "status": 409, "ticket_no": null}, {"request_id": "r000199", "user_id": "xu000199", "status": 409, "ticket_no": null}, {"request_id": "r000256", "user_id": "xu000256", "status": 409, "ticket_no": null}]`

## Throughput and latency

51090 responses in 49.6 s → **1030.0 req/s** handled; 0 without a response.

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1.7 | 1008.7 | 1522.6 | 1774.0 |
| service time (from actual send) | 1.2 | 1006.9 | 1450.7 | 1664.0 |
| client send lag | 0.4 | 1.1 | 71.4 | 239.8 |

Responses by HTTP status: `{'200': 1972, '409': 41180, '503': 7938}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000, 'replay_after_sellout': 50, 'rid_conflict': 20, 'same_user_new_rid': 20}`  
First sold-out answer at t = 9.339 s
