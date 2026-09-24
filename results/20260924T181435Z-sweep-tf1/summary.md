# Rate sweep: where does latency degrade, and why?

Target `http://lb:8080`. Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. Each seller instance is one Python process (one uvicorn worker, D11), so ~100% per instance is its ceiling; 'sellers CPU' sums all instances.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | sellers CPU mean/max | postgres CPU mean/max | nginx CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1500 | 1498.8 | 3.1 | 159.5 | 0 | 0.1/0.2 | 0.5/6.2 | 1.4/53.5 | 156%/256% | 49%/70% | 31%/47% | 0.7/55.9 | Client:ClientRead 65%; LWLock:WALWrite 19%; running (no wait = on CPU) 12% | 3.4 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **not reached**
