# Rate sweep: where does latency degrade, and why?

Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. The seller is one Python process (one uvicorn worker, D11), so ~100% is its ceiling.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | seller CPU mean/max | postgres CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 250 **← knee** | 250.0 | 2.7 | 184.9 | 0 | 0.0/0.2 | 0.5/25.3 | 1.0/101.2 | 32%/72% | 15%/37% | 0.1/17.1 | IO:DataFileImmediateSync 33%; running (no wait = on CPU) 33%; Client:ClientRead 33% | 2.2 | all PASS |
| 500 | 500.0 | 2.3 | 7.2 | 0 | 0.0/0.1 | 0.4/5.0 | 0.8/1.6 | 39%/62% | 19%/24% | 0.2/19.8 | running (no wait = on CPU) 100% | 1.2 | all PASS |
| 1000 | 999.9 | 2.3 | 37.7 | 0 | 0.0/0.3 | 0.4/8.3 | 0.8/8.4 | 65%/92% | 30%/44% | 0.1/19.9 | running (no wait = on CPU) 100% | 1.2 | all PASS |
| 1500 | 1498.9 | 4.9 | 729.7 | 8 | 0.0/464.1 | 0.9/11.1 | 1.4/665.5 | 88%/118% | 45%/71% | 0.1/19.9 | running (no wait = on CPU) 100% | 1.4 | all PASS |
| 2000 | 1511.0 | 1050.8 | 9613.3 | 15770 | 0.0/997.1 | 3.9/76.5 | 31.7/9607.4 | 92%/124% | 33%/74% | 0.2/19.8 | running (no wait = on CPU) 57%; Client:ClientRead 43% | 12.6 | all PASS |
| 2500 | 1347.4 | 1727.8 | 11235.8 | 22266 | 0.0/995.1 | 3.6/64.7 | 45.6/9873.0 | 85%/121% | 27%/62% | 0.1/19.9 | running (no wait = on CPU) 67%; Client:ClientRead 33% | 1717.1 | all PASS |
| 3000 | 1387.3 | 3505.3 | 13241.2 | 29435 | 0.0/995.0 | 4.4/63.1 | 39.1/10407.6 | 89%/127% | 33%/64% | 0.1/19.9 | Client:ClientRead 75%; IO:DataFileImmediateSync 12%; running (no wait = on CPU) 12% | 4691.3 | all PASS |
| 4000 | 1436.7 | 6090.5 | 18733.7 | 40303 | 0.0/991.0 | 3.8/68.8 | 61.8/9236.5 | 92%/123% | 28%/70% | 0.2/19.8 | Client:ClientRead 60%; running (no wait = on CPU) 30%; IO:DataFileImmediateSync 10% | 10628.6 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **250**
