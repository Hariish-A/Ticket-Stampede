# Rate sweep: where does latency degrade, and why?

Target `http://lb:8080`. Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. Each seller instance is one Python process (one uvicorn worker, D11), so ~100% per instance is its ceiling; 'sellers CPU' sums all instances.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | sellers CPU mean/max | postgres CPU mean/max | nginx CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1500 | 1499.6 | 3.6 | 122.2 | 0 | 0.1/6.1 | 0.6/7.9 | 1.6/28.4 | 196%/294% | 60%/81% | 36%/55% | 0.4/56.1 | Client:ClientRead 75%; running (no wait = on CPU) 25% | 1.5 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **not reached**
