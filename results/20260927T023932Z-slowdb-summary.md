# Postgres +3 s per answer for 10 s mid-sale (15,000-ticket sale; topology: single)

| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s | seller counters | client lag p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260927T023821Z-slowdb-failfast-256 | skiplocked | 15000 | all PASS | 4856.9 | 25.6 | 1176.2 | 10334.5 | 234351 | None | admission_shed=231045, claims=14310, unique_violation_retries=2 | 21.0 |

Latency is measured from each request's scheduled send time (open-loop). 'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling every ticket took. Seller counters come from GET /metrics, diffed across the run.

## Timelines side by side

| t s | open-loop sent | p99 ms |
|---|---|---|
| 0 | 2689 | 2560.6 |
| 1 | 2823 | 979.1 |
| 2 | 3062 | 1007.2 |
| 3 | 3364 | 1009.0 |
| 4 | 3195 | 1026.6 |
| 5 ⚡ | 3501 | 1015.6 |
| 6 ⚡ | 4125 | 1010.2 |
| 7 ⚡ | 4448 | 1019.3 |
| 8 ⚡ | 4929 | 1033.0 |
| 9 ⚡ | 5211 | 1150.9 |
| 10 ⚡ | 5458 | 1316.0 |
| 11 ⚡ | 5530 | 1052.2 |
| 12 ⚡ | 6290 | 1078.8 |
| 13 ⚡ | 6446 | 1097.9 |
| 14 ⚡ | 6801 | 1295.6 |
| 15 ⚡ | 5770 | 9611.5 |
| 16 | 6275 | 952.2 |
| 17 | 6095 | 957.4 |
| 18 | 5669 | 1024.4 |
| 19 | 6281 | 1155.6 |
| 20 | 6192 | 1093.7 |
| 21 | 6192 | 1028.2 |
| 22 | 6260 | 1157.7 |
| 23 | 6240 | 1042.3 |
| 24 | 6403 | 1066.7 |
| 25 | 6263 | 1073.0 |
| 26 | 6926 | 1125.8 |
| 27 | 7081 | 1097.3 |
| 28 | 7147 | 1257.3 |
| 29 | 7418 | 1314.4 |
| 30 | 6731 | 1198.3 |
| 31 | 7101 | 964.8 |
| 32 | 6931 | 1075.9 |
| 33 | 7477 | 1071.3 |
| 34 | 7362 | 960.9 |
| 35 | 6780 | 1133.6 |
| 36 | 6502 | 1089.8 |
| 37 | 7431 | 995.8 |
| 38 | 6718 | 823.6 |
| 39 | 5187 | 1017.1 |
| 40 | 3982 | 1017.3 |
| 41 | 3271 | 960.3 |
| 42 | 2756 | 1013.1 |
| 43 | 2565 | 1010.1 |
| 44 | 1961 | 1007.2 |
| 45 | 1440 | 884.0 |
| 46 | 1212 | 692.4 |
| 47 | 871 | 491.6 |
| 48 | 388 | 367.1 |
| 49 | 164 | 136.4 |
| 50 | 30 | 113.0 |
| 51 | 2 | 10.8 |
