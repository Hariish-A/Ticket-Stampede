# Hot row: commit flush on vs off (large sale, 5,000 tickets)

| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s | seller counters | client lag p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260924T093012Z-hotrow-counter-sync-on | counter | 5000 | all PASS | 1095.6 | 1008.6 | 2127.3 | 2504.3 | 16159 | None | claims=4787, unique_violation_retries=33 | 31.4 |
| 20260924T093037Z-hotrow-counter-sync-off | counter | 5000 | all PASS | 1098.7 | 1007.5 | 1701.8 | 2006.4 | 16237 | None | claims=4723, unique_violation_retries=23 | 43.1 |
| 20260924T093107Z-hotrow-skiplocked-sync-on | skiplocked | 5000 | all PASS | 1115.3 | 2.5 | 2691.8 | 3206.5 | 1834 | 4.713 | blocking_fallbacks=4, claims=5000, sold_out_checks=4, sold_out_fast=13977, unique_violation_retries=45 | 31.6 |
| 20260924T093131Z-hotrow-skiplocked-sync-off | skiplocked | 5000 | all PASS | 1114.4 | 2.4 | 1817.1 | 2411.9 | 2259 | 5.136 | blocking_fallbacks=4, claims=5000, sold_out_checks=4, sold_out_fast=13530, unique_violation_retries=83 | 29.7 |

Latency is measured from each request's scheduled send time (open-loop). 'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling every ticket took. Seller counters come from GET /metrics, diffed across the run.
