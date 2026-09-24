# Run `slowdb-baseline`

target `http://seller1:8000` · allocator **skiplocked** · open-loop, 4 processes · 15000 tickets · 187655 requests (burst 1000 at t=0, then 1000.0/s) · seed 1 · 2026-09-24T10:25:30+00:00 · client retries unclear answers up to 6x with the same request_id

**Fault injected:** latency +3000 ms on every response from Postgres (toxiproxy 'postgres'), planned t=5.0–15.0 s, actual t=5.0–15.0 s

## Invariants

| | Check | Verdict | Detail |
|---|---|---|---|
| I1 | Never sell more tickets than exist | **PASS** | 13307 confirmed, 15000 in /status, total 15000 |
| I2 | Never issue the same ticket number twice | **PASS** | every ticket number has exactly one holder |
| I3 | A repeated request_id gets one ticket, not two | **PASS** | 147705 duplicate/replayed requests, none produced a second ticket |
| I4 | /status count matches the tickets actually issued | **PASS** | sold=15000 = 15000 holders, every confirmed ticket present |
| U1 | One ticket per user (product rule D3) | **PASS** | no user holds two tickets |
| U2 | A winner's request_id reused by another user is never given a ticket (422) | **PASS** | 20 conflicting requests: 20 rejected (422), 0 never got a definite answer (503/timeout), 0 given a ticket |
| U3 | Nobody is told 'sold out' while tickets remain | **PASS** | 19544 sold-out answers, 15000/15000 issued |
| U4 | Every response belongs to this sale (no reset mid-run) | **PASS** | all responses epoch 758 |
| U5 | A buyer who holds a ticket is never told 'sold out' | **PASS** | 27597 repeat requests from holders, none told 'sold out' |
| A3 | Live audit: invariants held in every /status snapshot during the sale | **PASS** | 159 snapshots over 101.4s, 0 violations (33 polls got no answer) |
| A2 | Orphaned tickets (sold, but the buyer was never told) | **INFO** | 1693 tickets in /status were never confirmed to their buyer |

## Throughput and latency

Stampede: 111949 responses in 98.487 s → **1136.7 req/s** handled; 75706 without a response. Then 90 post-sale probes (verified, not timed).

| ms | p50 | p90 | p99 | max |
|---|---|---|---|---|
| latency (from scheduled send) | 1418.8 | 4510.3 | 9859.6 | 20964.5 |
| service time (from actual send) | 1417.8 | 4190.6 | 8966.4 | 13805.2 |
| client send lag | 0.0 | 11.4 | 8764.7 | 14656.1 |
| ↳ seller: waiting for a DB connection | 12.7 | 892.2 | 995.3 | 1219.8 |
| ↳ seller: allocator queries | 5.8 | 15.9 | 208.9 | 2638.8 |
| ↳ seller: whole handler | 1027.4 | 1355.1 | 1734.2 | 4483.5 |
| ↳ outside the handler (HTTP, event-loop queue, network) | 227.3 | 3080.8 | 8958.8 | 13789.8 |

Responses by HTTP status: `{'0': 75706, '200': 13661, '409': 19538, '503': 78750}`  
Requests by kind: `{'dup_concurrent': 500, 'dup_sequential': 500, 'fresh': 40000, 'retry': 146655}`  
Transport errors: `{'TimeoutError': 70674, 'ClientOSError': 4221, 'ClientConnectorError': 811}`  
First sold-out answer at t = 51.834 s  
Seller counters during the run (GET /metrics): `{'claims': 14987, 'unique_violation_retries': 34, 'blocking_fallbacks': 9, 'sold_out_checks': 9, 'sold_out_fast': 28121}`  
Client health: 4 worker processes, CPU per worker `['56%', '68%', '61%', '58%']` of one core; send lag p99 8764.7 ms. A worker near 100% or a growing send lag means the client, not the seller, was the limit.

## What each buyer ended up with (after retries)

40000 buyers (user, request_id): final answers `{'purchased': 13307, 'turned_away_known': 650, 'still_unknown': 6856, 'sold_out': 19187}`. 35422 got at least one unclear answer (503 or no response); **3036 of those had in fact bought** (a retry with the same request_id got the ticket back as a replay: the earlier 'unknown' had committed); 5738 bought on a later retry; `still_unknown` = never got a definite answer.

Answers by kind: `{'no_response': 75706, 'not_attempted': 78736, 'purchased': 13661, 'sold_out': 19538, 'unknown': 14}`

## Timeline (1 s buckets, by scheduled send time)

| t s | sent | retries | purchased | sold out | unknown | not attempted | no response | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 2043 | 0 | 1340 | 0 | 0 | 703 | 0 | 1123.0 | 2465.7 |
| 1 | 1309 | 279 | 850 | 0 | 0 | 459 | 0 | 666.9 | 1066.8 |
| 2 | 1663 | 646 | 1311 | 0 | 0 | 352 | 0 | 604.1 | 1022.3 |
| 3 | 1424 | 397 | 1370 | 0 | 0 | 54 | 0 | 494.9 | 1020.7 |
| 4 | 1247 | 226 | 802 | 0 | 8 | 437 | 0 | 488.5 | 1093.3 |
| 5 ⚡ | 1133 | 104 | 0 | 0 | 1 | 1132 | 0 | 1001.8 | 1123.3 |
| 6 ⚡ | 1968 | 945 | 0 | 0 | 0 | 1968 | 0 | 1016.6 | 1253.6 |
| 7 ⚡ | 2312 | 1284 | 0 | 0 | 0 | 2312 | 0 | 1095.5 | 1632.1 |
| 8 ⚡ | 2924 | 1907 | 0 | 0 | 0 | 2924 | 0 | 1216.9 | 4276.0 |
| 9 ⚡ | 2778 | 1753 | 0 | 0 | 0 | 2043 | 735 | 1276.1 | 1419.8 |
| 10 ⚡ | 2943 | 1915 | 0 | 0 | 0 | 2259 | 684 | 1387.1 | 1680.3 |
| 11 ⚡ | 3388 | 2374 | 0 | 0 | 0 | 2121 | 1267 | 1400.0 | 1603.1 |
| 12 ⚡ | 3037 | 2003 | 0 | 0 | 0 | 2651 | 386 | 1373.7 | 1656.2 |
| 13 ⚡ | 2803 | 1777 | 0 | 0 | 0 | 1895 | 908 | 1536.2 | 1890.8 |
| 14 ⚡ | 3262 | 2247 | 0 | 0 | 0 | 2128 | 1134 | 1541.2 | 2081.1 |
| 15 ⚡ | 3066 | 2033 | 0 | 0 | 0 | 2362 | 704 | 1477.2 | 1644.1 |
| 16 | 2810 | 1783 | 0 | 0 | 0 | 1282 | 1528 | 1787.3 | 1958.9 |
| 17 | 3235 | 2209 | 0 | 0 | 0 | 2332 | 903 | 1501.8 | 1869.0 |
| 18 | 2885 | 1860 | 0 | 0 | 0 | 2181 | 704 | 1473.3 | 1952.0 |
| 19 | 2996 | 1962 | 0 | 0 | 0 | 1842 | 1154 | 1638.2 | 1936.7 |
| 20 | 3333 | 2310 | 0 | 0 | 0 | 1842 | 1491 | 1748.9 | 1940.0 |
| 21 | 3663 | 2636 | 0 | 0 | 0 | 2290 | 1373 | 1807.2 | 3255.4 |
| 22 | 3309 | 2290 | 0 | 0 | 0 | 1846 | 1463 | 2216.3 | 3181.2 |
| 23 | 3335 | 2312 | 15 | 0 | 0 | 1255 | 2065 | 3388.8 | 7199.4 |
| 24 | 2594 | 1567 | 0 | 0 | 0 | 1306 | 1288 | 3715.1 | 5863.3 |
| 25 | 3455 | 2434 | 13 | 0 | 3 | 1275 | 2164 | 4512.3 | 6298.7 |
| 26 | 1728 | 702 | 42 | 0 | 2 | 587 | 1097 | 5868.4 | 6565.5 |
| 27 | 1483 | 461 | 9 | 0 | 0 | 469 | 1005 | 5044.8 | 5865.0 |
| 28 | 1906 | 880 | 0 | 0 | 0 | 922 | 984 | 3955.2 | 5097.3 |
| 29 | 1719 | 701 | 0 | 0 | 0 | 629 | 1090 | 2968.3 | 9970.3 |
| 30 | 3239 | 2220 | 73 | 0 | 0 | 1250 | 1916 | 2817.8 | 9820.6 |
| 31 | 1870 | 846 | 44 | 0 | 0 | 5 | 1821 | 1460.3 | 6043.4 |
| 32 | 4168 | 3139 | 54 | 0 | 0 | 2228 | 1886 | 6332.5 | 9260.4 |
| 33 | 2217 | 1192 | 220 | 0 | 0 | 701 | 1296 | 4534.2 | 18006.6 |
| 34 | 1910 | 872 | 74 | 30 | 0 | 0 | 1806 | 10144.6 | 17993.7 |
| 35 | 2606 | 1576 | 621 | 26 | 0 | 277 | 1682 | 2990.8 | 17594.8 |
| 36 | 2177 | 1152 | 17 | 0 | 0 | 2 | 2158 | 1959.2 | 1967.6 |
| 37 | 2309 | 1281 | 432 | 0 | 0 | 275 | 1602 | 3468.2 | 13906.0 |
| 38 | 2925 | 1908 | 387 | 0 | 0 | 709 | 1829 | 2601.0 | 13230.8 |
| 39 | 1921 | 1910 | 149 | 0 | 0 | 633 | 1139 | 3251.1 | 4052.4 |
| 40 | 1373 | 1373 | 105 | 0 | 0 | 0 | 1268 | 3107.1 | 4062.0 |
| 41 | 2597 | 2597 | 529 | 61 | 0 | 1147 | 860 | 4622.3 | 10175.5 |
| 42 | 1726 | 1726 | 423 | 66 | 0 | 201 | 1036 | 2926.1 | 11141.3 |
| 43 | 1121 | 1121 | 266 | 0 | 0 | 22 | 833 | 2602.8 | 5011.2 |
| 44 | 1941 | 1941 | 230 | 0 | 0 | 619 | 1092 | 3884.3 | 6416.7 |
| 45 | 1334 | 1334 | 360 | 0 | 0 | 486 | 488 | 5503.5 | 6077.4 |
| 46 | 1405 | 1405 | 339 | 0 | 0 | 233 | 833 | 4953.8 | 5033.5 |
| 47 | 835 | 835 | 87 | 0 | 0 | 0 | 748 | 1542.2 | 4167.3 |
| 48 | 2233 | 2233 | 731 | 19 | 0 | 271 | 1212 | 3397.1 | 3535.3 |
| 49 | 968 | 968 | 21 | 88 | 0 | 8 | 851 | 2862.4 | 3512.5 |
| 50 | 753 | 753 | 0 | 0 | 0 | 0 | 753 | - | - |
| 51 | 3344 | 3344 | 67 | 560 | 0 | 1262 | 1455 | 2503.5 | 3423.0 |
| 52 | 2103 | 2103 | 12 | 86 | 0 | 621 | 1384 | 3095.8 | 3147.4 |
| 53 | 2348 | 2348 | 74 | 438 | 0 | 212 | 1624 | 1044.1 | 1803.1 |
| 54 | 3068 | 3068 | 145 | 625 | 0 | 499 | 1799 | 2080.6 | 2888.9 |
| 55 | 3046 | 3046 | 99 | 547 | 0 | 1184 | 1216 | 1976.7 | 2961.9 |
| 56 | 2866 | 2866 | 37 | 160 | 0 | 944 | 1725 | 2013.0 | 2837.3 |
| 57 | 1859 | 1859 | 54 | 508 | 0 | 152 | 1145 | 1186.0 | 2123.3 |
| 58 | 2317 | 2317 | 97 | 322 | 0 | 1019 | 879 | 1427.6 | 1679.4 |
| 59 | 2963 | 2963 | 53 | 307 | 0 | 1422 | 1181 | 1264.3 | 2993.3 |
| 60 | 1677 | 1677 | 51 | 517 | 0 | 459 | 650 | 874.8 | 1209.8 |
| 61 | 1341 | 1341 | 94 | 651 | 0 | 163 | 433 | 32.5 | 1196.7 |
| 62 | 2748 | 2748 | 76 | 362 | 0 | 1363 | 947 | 1133.3 | 1474.9 |
| 63 | 1996 | 1996 | 82 | 403 | 0 | 506 | 1005 | 1020.7 | 1266.4 |
| 64 | 2383 | 2383 | 45 | 285 | 0 | 1204 | 849 | 1055.9 | 1302.5 |
| 65 | 2909 | 2909 | 99 | 471 | 0 | 1428 | 911 | 1074.9 | 1393.6 |
| 66 | 2810 | 2810 | 30 | 238 | 0 | 1543 | 999 | 1260.6 | 1610.6 |
| 67 | 2924 | 2924 | 33 | 251 | 0 | 1738 | 902 | 1261.8 | 1687.0 |
| 68 | 2232 | 2232 | 39 | 231 | 0 | 1162 | 800 | 1329.8 | 1608.3 |
| 69 | 2003 | 2003 | 47 | 382 | 0 | 1043 | 531 | 1104.8 | 1294.3 |
| 70 | 2258 | 2258 | 52 | 408 | 0 | 1173 | 625 | 1059.4 | 1237.6 |
| 71 | 2714 | 2714 | 41 | 472 | 0 | 1518 | 683 | 1065.7 | 1314.7 |
| 72 | 1980 | 1980 | 67 | 606 | 0 | 916 | 391 | 1021.4 | 1200.5 |
| 73 | 1670 | 1670 | 89 | 767 | 0 | 422 | 392 | 901.5 | 10342.2 |
| 74 | 1602 | 1602 | 77 | 529 | 0 | 667 | 329 | 1095.2 | 10161.3 |
| 75 | 1808 | 1808 | 76 | 772 | 0 | 750 | 210 | 1036.7 | 10004.3 |
| 76 | 1760 | 1760 | 60 | 755 | 0 | 408 | 537 | 1012.6 | 10175.6 |
| 77 | 1272 | 1272 | 80 | 829 | 0 | 33 | 330 | 1003.5 | 10428.6 |
| 78 | 868 | 868 | 74 | 677 | 0 | 0 | 117 | 124.9 | 9570.7 |
| 79 | 1311 | 1311 | 115 | 903 | 0 | 0 | 293 | 193.4 | 10150.8 |
| 80 | 888 | 888 | 79 | 768 | 0 | 0 | 41 | 162.1 | 10358.2 |
| 81 | 914 | 914 | 78 | 820 | 0 | 0 | 16 | 5742.1 | 10095.7 |
| 82 | 538 | 538 | 47 | 485 | 0 | 0 | 6 | 5788.6 | 9093.1 |
| 83 | 495 | 495 | 68 | 427 | 0 | 0 | 0 | 82.6 | 8166.3 |
| 84 | 582 | 582 | 101 | 473 | 0 | 0 | 8 | 53.4 | 181.0 |
| 85 | 611 | 611 | 99 | 508 | 0 | 0 | 4 | 48.4 | 147.3 |
| 86 | 344 | 344 | 72 | 272 | 0 | 0 | 0 | 14.9 | 143.2 |
| 87 | 198 | 198 | 40 | 158 | 0 | 0 | 0 | 18.6 | 201.9 |
| 88 | 475 | 475 | 55 | 420 | 0 | 0 | 0 | 14.3 | 176.0 |
| 89 | 351 | 351 | 43 | 308 | 0 | 0 | 0 | 17.9 | 186.4 |
| 90 | 196 | 196 | 24 | 172 | 0 | 0 | 0 | 12.7 | 159.7 |
| 91 | 180 | 180 | 20 | 149 | 0 | 0 | 11 | 10.3 | 164.7 |
| 92 | 141 | 141 | 25 | 98 | 0 | 0 | 18 | 31.2 | 181.1 |
| 93 | 115 | 115 | 23 | 81 | 0 | 0 | 11 | 37.0 | 173.7 |
| 94 | 37 | 37 | 6 | 22 | 0 | 0 | 9 | 10.0 | 73.9 |
| 95 | 16 | 16 | 1 | 11 | 0 | 0 | 4 | 3.1 | 118.4 |
| 96 | 7 | 7 | 1 | 6 | 0 | 0 | 0 | 10.0 | 88.8 |
| 97 | 6 | 6 | 0 | 6 | 0 | 0 | 0 | 51.6 | 81.0 |
| 98 | 2 | 2 | 0 | 2 | 0 | 0 | 0 | 26.7 | 26.7 |

⚡ = fault active (t=5.0–15.0 s)
