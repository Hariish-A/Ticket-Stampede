# M7 / TF2: SIGKILL Postgres mid-sale, restart after 5 s (3 normal runs + synchronous_commit=off control)

| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s | seller counters | client lag p99 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20260924T173849Z-killdb-1 | skiplocked | 15000 | all PASS | 398.9 | 1036.3 | 3588.2 | 5650.4 | 39072 | 69.801 | blocking_fallbacks=18, claims=15000, sold_out_checks=18, sold_out_fast=25429, unique_violation_retries=20 | 362.2 |
| 20260924T174224Z-killdb-2 | skiplocked | 15000 | all PASS | 423.5 | 1034.2 | 3555.7 | 5345.9 | 35051 | 48.96 | blocking_fallbacks=5, claims=14995, sold_out_checks=5, sold_out_fast=25469, unique_violation_retries=16 | 301.5 |
| 20260924T174602Z-killdb-3 | skiplocked | 15000 | all PASS | 369.1 | 1037.4 | 3961.8 | 10377.1 | 41218 | 84.939 | blocking_fallbacks=15, claims=14996, sold_out_checks=15, sold_out_fast=25416, unique_violation_retries=14 | 459.2 |
| 20260924T175008Z-killdb-off | skiplocked | 15000 | FAIL: I1, I2, I4 | 452.4 | 1005.8 | 2543.9 | 5403.1 | 29764 | 34.239 | blocking_fallbacks=6, claims=15006, sold_out_checks=6, sold_out_fast=25542, unique_violation_retries=28 | 226.8 |

Latency is measured from each request's scheduled send time (open-loop). 'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling every ticket took. Seller counters come from GET /metrics, diffed across the run.
