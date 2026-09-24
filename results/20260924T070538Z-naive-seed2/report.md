# Run `naive-seed2`

target `http://seller1:8000` · allocator **naive** · 100 tickets · 51090 requests (burst 1000 at t=0, then 1000/s) · seed 2 · 2026-09-24T07:05:38+00:00

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **FAIL** | /status lists 1811 holders > total=100; buyers were confirmed 1807 distinct tickets > total=100 |
| I2 | Never issue the same ticket number twice | **FAIL** | /status has 1711 repeated ticket numbers; 100 ticket numbers confirmed to more than one user |
| I3 | A repeated request_id gets one ticket, not two | **FAIL** | 3 request_ids received more than one ticket |
| I4 | /status count matches the tickets actually issued | **FAIL** | /status sold=100 but lists 1811 holders |
| U1 | One ticket per user (product rule D3) | **FAIL** | 3 users hold more than one ticket |
| U2 | request_id reused by another user is rejected (422) | **FAIL** | 20/20 conflicting requests were not rejected |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 43326 sold-out answers, 1811/100 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 3 |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 0 tickets in /status were never confirmed to their buyer |

Examples of failures:

- I2: `[{"ticket_no": 48, "users": ["u004049", "u004076", "u004083", "u004102", "u004155", "u004227", "u004234", "u004243", "u004244", "u004501", "u004502", "u004503", "u004504", "u004505", "u004506", "u004507", "u004508", "u004509", "u004510", "u004511", "u004512", "u005229", "u005252", "u005479", "u005480", "u005493", "u005495"]}, {"ticket_no": 72, "users": ["u005785", "u005793", "u005857", "u005879", "u005901", "u005910", "u005918", "u005940", "u005943", "u005997", "u006843", "u006876", "u006962"]}, {"ticket_no": 30, "users": ["u002594", "u002881", "u003018", "u003044", "u003069", "u003085", "u003093", "u003152", "u003155", "u003163", "u003174", "u003195", "u003201", "u003232", "u003264", "u003267", "u003299", "u003303", "u003857", "u004126", "u004614"]}]`
- I3: `[{"request_id": "r003357", "tickets": [18, 34]}, {"request_id": "r004637", "tickets": [53, 60]}, {"request_id": "r006091", "tickets": [77, 90]}]`
- U1: `[{"user_id": "u003357", "tickets": [18, 34]}, {"user_id": "u006091", "tickets": [77, 90]}, {"user_id": "u004637", "tickets": [53, 60]}]`
- U2: `[{"request_id": "r000003", "user_id": "xu000003", "status": 409, "ticket_no": null}, {"request_id": "r000039", "user_id": "xu000039", "status": 409, "ticket_no": null}, {"request_id": "r000105", "user_id": "xu000105", "status": 409, "ticket_no": null}]`

## Throughput and latency

51090 responses in 49.786 s → **1026.2 req/s** handled; 0 without a response.

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1.7 | 1002.2 | 1536.6 | 1692.6 |
| service time (from actual send) | 1.2 | 1001.6 | 1486.4 | 1644.2 |
| client send lag | 0.4 | 1.1 | 79.1 | 265.5 |

Responses by HTTP status: `{'200': 1811, '409': 43326, '503': 5953}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 50000, 'replay_after_sellout': 50, 'rid_conflict': 20, 'same_user_new_rid': 20}`  
First sold-out answer at t = 7.151 s
