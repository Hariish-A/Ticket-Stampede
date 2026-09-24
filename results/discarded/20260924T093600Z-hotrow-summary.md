# Hot row: commit flush on vs off (large sale, 5,000 tickets)

| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s | seller counters | client lag p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260924T093419Z-hotrow-counter-sync-on | counter | 5000 | all PASS | 1113.8 | 1006.8 | 2324.4 | 2532.4 | 12175 | 15.375 | claims=5000, sold_out_checks=19, sold_out_fast=3736, unique_violation_retries=30 | 38.2 |
| 20260924T093443Z-hotrow-counter-sync-off | counter | 5000 | all PASS | 1113.7 | 1004.6 | 1808.0 | 2012.2 | 13170 | 16.297 | claims=5000, sold_out_checks=19, sold_out_fast=2732, unique_violation_retries=39 | 33.1 |
| 20260924T093512Z-hotrow-skiplocked-sync-on | skiplocked | 5000 | all PASS | 1114.4 | 2.4 | 3847.7 | 4636.5 | 1956 | 5.034 | blocking_fallbacks=10, claims=5000, sold_out_checks=10, sold_out_fast=13843, unique_violation_retries=41 | 30.5 |
| 20260924T093536Z-hotrow-skiplocked-sync-off | skiplocked | 5000 | all PASS | 1114.1 | 2.4 | 1684.8 | 2252.0 | 2119 | 5.004 | blocking_fallbacks=4, claims=5000, sold_out_checks=4, sold_out_fast=13666, unique_violation_retries=74 | 32.5 |

Latency is measured from each request's scheduled send time (open-loop). 'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling every ticket took. Seller counters come from GET /metrics, diffed across the run.
