# Rate sweep: where does latency degrade, and why?

Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. The seller is one Python process (one uvicorn worker, D11), so ~100% is its ceiling.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | seller CPU mean/max | postgres CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 500 | 499.7 | 3.6 | 316.8 | 0 | 0.0/12.2 | 1.4/51.5 | 1.0/286.8 | 41%/61% | 27%/43% | 0.1/14.1 | IO:DataFileImmediateSync 50%; Client:ClientRead 50% | 1.3 | all PASS |
| 2000 **← knee** | 1103.0 | 1022.8 | 4522.0 | 3003 | 0.0/998.3 | 10.2/69.1 | 17.5/4500.6 | 94%/121% | 64%/96% | 0.1/19.9 | IO:DataFileImmediateSync 50%; running (no wait = on CPU) 50% | 15.9 | all PASS |

Knee (first rate with p99 > 3x the lowest rate's, >0.1% errors, or <95% of offered handled): **2000**
