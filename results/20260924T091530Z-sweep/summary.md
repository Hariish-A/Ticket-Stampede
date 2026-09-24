# Rate sweep: where does latency degrade, and why?

Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. The seller is one Python process (one uvicorn worker, D11), so ~100% is its ceiling.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | seller CPU mean/max | postgres CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 250 | 250.0 | 3.9 | 7.3 | 0 | 0.0/0.1 | 1.3/4.0 | 1.0/1.8 | 38%/77% | 23%/35% | 0.1/5.8 | running (no wait = on CPU) 100% | 2.2 | all PASS |
| 500 | 499.9 | 3.4 | 8.6 | 0 | 0.0/0.1 | 1.2/5.0 | 0.9/1.9 | 54%/83% | 36%/48% | 0.1/19.9 | running (no wait = on CPU) 67%; Client:ClientRead 33% | 1.3 | all PASS |
| 1000 **← knee** | 999.4 | 4.3 | 309.8 | 0 | 0.0/279.8 | 1.8/24.4 | 1.0/53.6 | 85%/118% | 58%/91% | 0.4/19.6 | Client:ClientRead 53%; running (no wait = on CPU) 47% | 1.3 | all PASS |
| 1500 | 1414.7 | 1025.1 | 5123.5 | 14615 | 0.0/999.5 | 15.4/222.3 | 15.0/4897.3 | 83%/125% | 45%/94% | 0.4/19.6 | running (no wait = on CPU) 50%; Client:ClientRead 43%; IO:WALSync 7% | 6.2 | all PASS |
| 2000 | 1106.5 | 1059.3 | 10417.4 | 22064 | 0.0/997.5 | 13.2/269.9 | 29.8/10307.9 | 90%/126% | 48%/100% | 0.2/19.8 | running (no wait = on CPU) 60%; Client:ClientRead 40% | 126.3 | all PASS |
| 2500 | 1062.5 | 2550.2 | 12286.4 | 27858 | 0.0/997.6 | 11.5/275.5 | 49.1/10642.0 | 87%/127% | 50%/97% | 0.2/19.8 | running (no wait = on CPU) 57%; Client:ClientRead 43% | 2315.2 | all PASS |
| 3000 | 1187.5 | 4481.5 | 13588.0 | 38073 | 0.0/998.5 | 17.8/428.2 | 59.6/9022.8 | 87%/126% | 37%/79% | 0.3/19.7 | running (no wait = on CPU) 53%; Client:ClientRead 47% | 6705.1 | all PASS |
| 4000 | 1187.0 | 7100.1 | 21262.7 | 48877 | 0.0/995.9 | 13.9/370.1 | 59.0/9961.5 | 91%/132% | 50%/98% | 0.1/19.9 | Client:ClientRead 60%; running (no wait = on CPU) 40% | 14526.3 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **1000**
