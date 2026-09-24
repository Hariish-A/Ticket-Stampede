# Rate sweep: where does latency degrade, and why?

Target `http://lb:8080`. Steady open-loop load on the sold-out path (100 tickets, sold out in the first moments), one row per offered rate. CPU: 100% = one core. Each seller instance is one Python process (one uvicorn worker, D11), so ~100% per instance is its ceiling; 'sellers CPU' sums all instances.

| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 | sellers CPU mean/max | postgres CPU mean/max | nginx CPU mean/max | PG active/idle conns | PG top waits (active) | client lag p99 | invariants |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1000 | 999.8 | 3.3 | 17.9 | 0 | 0.1/0.2 | 0.5/4.6 | 1.5/7.4 | 145%/244% | 33%/55% | 21%/34% | 0.2/33.4 | Client:ClientRead 50%; LWLock:WALWrite 33%; IO:WALSync 17% | 1.7 | all PASS |
| 2000 **← knee** | 1996.3 | 7.0 | 629.5 | 0 | 0.1/348.6 | 1.3/26.3 | 2.6/546.4 | 233%/474% | 82%/144% | 52%/88% | 0.5/54.1 | Client:ClientRead 71%; running (no wait = on CPU) 29% | 3.6 | all PASS |
| 3000 | 2152.2 | 1047.3 | 10029.5 | 23549 | 0.1/997.5 | 9.2/80.5 | 37.6/10001.6 | 236%/389% | 57%/135% | 60%/109% | 0.3/59.7 | Client:ClientRead 89%; running (no wait = on CPU) 11% | 49.2 | all PASS |
| 4000 | 3493.9 | 973.9 | 10143.1 | 11860 | 0.1/994.5 | 4.8/49.9 | 67.7/10134.7 | 164%/342% | 41%/87% | 59%/115% | 0.1/59.9 | Client:ClientRead 100% | 294.7 | all PASS |
| 5000 | 4704.3 | 326.2 | 10515.3 | 6100 | 0.1/995.0 | 5.0/40.2 | 490.3/10598.2 | 171%/308% | 50%/106% | 75%/186% | 0.2/59.8 | Client:ClientRead 83%; running (no wait = on CPU) 17% | 922.9 | all PASS |
| 6000 | 5493.1 | 1895.7 | 11401.1 | 6042 | 0.1/965.0 | 5.5/51.8 | 2504.5/10874.4 | 145%/295% | 44%/92% | 95%/227% | 0.1/59.9 | Client:ClientRead 80%; running (no wait = on CPU) 20% | 2447.5 | all PASS |

Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): **2000**
