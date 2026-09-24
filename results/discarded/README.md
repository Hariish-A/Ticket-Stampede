# Discarded runs

- `20260924T092023Z-sweep` (+ its sweep-* runs): the "after fast path" sweep whose first step measured a cold start (freshly recreated container, p99 185 ms at 250 req/s). Superseded by a rerun with a discarded warm-up step.
- `20260924T091232Z-sweep`, `*-sweep-500`, `*-sweep-2000`: 5-second smoke test of the sweep script.
- `20260924T0930*-hotrow-*` and `20260924T093154Z-hotrow-summary.md`: INVALID. The "sync-off" runs were really synchronous_commit=on. The script used ALTER SYSTEM, which the postgres command-line flag outranks; this was caught by the script printing SHOW synchronous_commit. Rerun with ALTER DATABASE plus a seller restart.
- `*-d10-direct`, `*-d10-hostfwd`, `20260924T093000Z-d10-summary.md`: one run per path, dominated by a single outlier. Superseded by alternating repetitions.
- `20260924T0934*`–`0936*` hotrow and d10 runs: a second attempt where the script fixes never applied (the Python edit script had a syntax error), so these repeat both flaws above.
