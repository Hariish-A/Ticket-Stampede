# Rate sweep: where does latency degrade, and why?

Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. The seller is one Python process (one uvicorn worker, D11), so ~100% is its ceiling.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | seller CPU mean/max | postgres CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 250 | 250.0 | 2.8 | 6.4 | 0 | 0.0/0.1 | 0.5/3.8 | 1.0/1.8 | 32%/52% | 13%/16% | 0.1/19.9 | IO:WALSync 50%; running (no wait = on CPU) 50% | 2.2 | all PASS |
| 500 | 500.0 | 2.4 | 6.8 | 0 | 0.0/0.1 | 0.4/4.3 | 0.9/1.6 | 43%/77% | 20%/28% | 0.1/19.9 | running (no wait = on CPU) 100% | 1.3 | all PASS |
| 1000 | 999.8 | 2.4 | 15.2 | 0 | 0.0/0.1 | 0.4/3.7 | 0.8/3.7 | 68%/93% | 33%/45% | 0.1/19.9 | running (no wait = on CPU) 67%; Client:ClientRead 33% | 1.2 | all PASS |
| 1500 **← knee** | 1480.7 | 4.7 | 521.6 | 2 | 0.0/463.2 | 0.9/11.3 | 1.4/315.1 | 85%/131% | 46%/70% | 0.3/19.7 | Client:ClientRead 67%; running (no wait = on CPU) 25%; IO:DataFileImmediateSync 8% | 1.4 | all PASS |
| 2000 | 1519.1 | 1043.8 | 10218.3 | 15632 | 0.0/998.9 | 4.1/60.9 | 28.1/10213.5 | 89%/124% | 33%/66% | 0.1/19.9 | running (no wait = on CPU) 50%; Client:ClientRead 50% | 11.0 | all PASS |
| 2500 | 1394.5 | 1597.1 | 10997.7 | 22089 | 0.0/996.7 | 3.8/58.3 | 38.8/9984.3 | 89%/123% | 30%/63% | 0.2/19.8 | running (no wait = on CPU) 62%; Client:ClientRead 38% | 1633.5 | all PASS |
| 3000 | 1376.3 | 3802.2 | 13591.0 | 30180 | 0.0/996.5 | 4.9/65.6 | 38.4/10479.2 | 89%/124% | 32%/70% | 0.1/19.9 | Client:ClientRead 67%; running (no wait = on CPU) 33% | 4842.4 | all PASS |
| 4000 | 1413.0 | 6495.8 | 19555.9 | 38645 | 0.0/994.3 | 3.6/76.7 | 63.8/9826.1 | 91%/125% | 30%/67% | 0.1/19.9 | Client:ClientRead 86%; running (no wait = on CPU) 14% | 11001.4 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **1500**
