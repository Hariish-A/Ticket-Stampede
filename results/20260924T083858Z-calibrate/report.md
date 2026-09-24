# Client calibration `calibrate`

Target `http://lb:8081` answers every request with a canned response and does no other work, so these numbers are the ceiling of the **client**, not of any seller. 5.0 s per row. 2026-09-24T08:38:58+00:00

| mode | processes | achieved req/s | send lag p50 ms | send lag p99 ms | latency p99 ms | worker CPU (max) | no response |
|---|---|---|---|---|---|---|---|
| closed-loop x128 | 1 | **4834.5** | 0.0 | 0.0 | 47.1 | 100% | 0 |
| closed-loop x256 | 2 | **8185.5** | 0.0 | 0.0 | 93.5 | 100% | 0 |
| closed-loop x512 | 4 | **12687.8** | 0.0 | 0.0 | 77.6 | 100% | 0 |
| closed-loop x1024 | 8 | **20657.3** | 0.0 | 0.0 | 97.7 | 99% | 0 |
| open-loop @ 10300/s | 8 | **10190.2** | 0.5 | 3.2 | 14.5 | 50% | 0 |

Closed-loop rows measure the ceiling (send lag is 0 by construction there). The open-loop row checks that at half the best ceiling the client keeps its schedule.
