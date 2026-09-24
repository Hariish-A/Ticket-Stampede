# Hot row: commit flush on vs off (large sale, 5,000 tickets)

| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s | seller counters | client lag p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260924T093752Z-hotrow-counter-sync-on | counter | 5000 | all PASS | 1093.1 | 1007.6 | 1895.1 | 2037.4 | 16062 | None | claims=4882, unique_violation_retries=34 | 31.7 |
| 20260924T093821Z-hotrow-counter-sync-off | counter | 5000 | all PASS | 1114.7 | 2.5 | 3051.4 | 3250.0 | 568 | 3.763 | claims=5000, sold_out_checks=5, sold_out_fast=15195, unique_violation_retries=45 | 29.5 |
| 20260924T093853Z-hotrow-skiplocked-sync-on | skiplocked | 5000 | all PASS | 1114.5 | 2.5 | 2547.5 | 3320.7 | 2357 | 5.215 | blocking_fallbacks=5, claims=5000, sold_out_checks=5, sold_out_fast=13448, unique_violation_retries=57 | 31.6 |
| 20260924T093921Z-hotrow-skiplocked-sync-off | skiplocked | 5000 | all PASS | 1114.5 | 2.3 | 2150.5 | 2609.2 | 1839 | 4.737 | claims=5000, sold_out_fast=13949, unique_violation_retries=55 | 31.9 |

Latency is measured from each request's scheduled send time (open-loop). 'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling every ticket took. Seller counters come from GET /metrics, diffed across the run.
