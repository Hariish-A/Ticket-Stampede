# M6: the datastore goes slow for 10 s in the middle of the sale

**Setup.** Postgres sits behind toxiproxy. The buyer itself adds **+3 s to every answer from Postgres** at t=5 s and removes it at t=15 s, on its own clock, so the fault window lines up with the timelines. 3 s is longer than the seller's 2 s query timeout, so during the stall **purchases commit in Postgres while the seller gives up and answers 503 "unknown"**. The sale is 15,000 tickets for 40,000 buyers (1,000 at t=0, then 1,000/s), still selling when the stall hits. With the brief's 100 tickets the sale is over in about 0.1 s, and a stall at t=5 s would only ever hit sold-out answers. Buyers retry unclear answers with the **same request_id**, up to 6 times, with exponential backoff and jitter. [Full comparison and timelines](20260924T103515Z-slowdb-final-summary.md).

## 1. Correctness: held in every variant
I1–I4, U1–U5 and the live audit (A3, `/status` polled throughout) PASS in all five runs. No oversell, no duplicate ticket, no confirmed sale missing from `/status`. The stall never produced a wrong answer; it produced *late* answers and *no* answers.

## 2. The finding: a 10 s stall became a ~40 s+ outage, driven by retries

| variant | orphaned tickets¹ | recovered by retry² | never got a definite answer | turned away (known: not bought)³ | sold out at | p99 (whole run) |
|---|---|---|---|---|---|---|
| **baseline** (no protection) | **1,693** | 3,036 | **6,856** | 650 | 51.8 s | 9.9 s |
| seller fail-fast (`MAX_INFLIGHT=64`) | 29 | 38 | 859 | 20,958 | 44.3 s | 0.94 s |
| client retry budget (200 retries/s) | **0** | 104 | **0** | 0 | **27.9 s** | 1.5 s |
| both | **0** | 103 | **0** | 0 | 30.3 s | 1.0 s |
| closed-loop client, no protection (C4) | 0 | 3 | 0 | 0 | 46.7 s | **0.07 s** |

¹ Sold (in `/status`) but the buyer never got a confirmation, even after retries.
² A retry with the same request_id got the ticket back as a *replay*: the earlier "unknown" had in fact committed.
³ Every answer was `503 not_attempted` (nothing was sent to the database), so this buyer definitely did not buy.

**Baseline.**
- The stall ended at t=15 s. The seller did not recover: p99 was still 18 s at t=33–35.
- Load was offered at ~3,000 req/s: 1,000 new plus ~2,000 retries, about twice the ~1,500 req/s one seller handles (M5). So the overload sustained itself after its trigger was gone. This is a **metastable failure**.
- Almost every 503 was `not_attempted`: requests queued a full second for one of 20 connections, then gave up. Each one burned CPU and a pool wait, and came back as another retry.

**Why each fix works, and what it costs:**
- **Client retry budget** (token bucket; over-budget retries *wait*, they are never dropped): offered load stays near 1,200 req/s through the stall, so there is no storm. Every buyer ends with a definite answer and **every orphan is recovered**. This is the root-cause fix. It needs clients we control: the official web or app client.
- **Seller fail-fast** (a pure ASGI middleware sheds `/buy` beyond 64 in flight with an immediate 503, before FastAPI parses anything): the seller stays responsive. p99 is back to 200–500 ms right after the stall, and orphans drop 1,693 → 29. A shed request is cheap: the seller answered ~4,500 req/s. I had doubted this, because M5 showed the web stack dominates per-request cost; the measurement says shedding *before* the framework is cheap enough. But against clients who retry without a budget, it turns the storm into ~21k "try again" answers, and those buyers run out of retries.
- **Both**: the budget's complete outcomes plus fail-fast's recovery latency. Production answer: fail-fast in the seller, because we cannot trust every client, plus a retry budget in the clients we ship.

## 3. C4: the closed-loop client hides the stall
Same stall, same seller. The closed-loop client (4 in flight, ~the same 1,000 req/s beforehand) reports **p99 65 ms**. The open-loop baseline reports 9.9 s. The timeline shows why: the closed-loop client sent **0–3 requests per second** during the 10 s stall, because each of its 4 loops waited for an answer before sending the next. The people who would have arrived during those 10 s are simply missing from its statistics. That is coordinated omission, measured.

## Also changed in M6
- **Two kinds of 503.** `not_attempted` (no connection was obtained, nothing sent: *known* not bought) vs `unknown` (a statement was sent and no answer came back: *maybe* bought). This was the M1 known weakness.
- **An answer is not discarded because releasing the connection failed.** If the allocator already returned a definite result and only releasing the connection errors, the seller returns the result, not a 503.
- **Failure logging is throttled** (first 20, then 1 in 500). A stall fails thousands of requests a second, and M5 showed CPU is the bottleneck.

## Mistakes caught in M6 (runs moved to `discarded/` with reasons)
1. The first client held its in-flight slot through retry backoff sleeps, so sleeping retries throttled *new* sends (client lag up to 67 s). That is the client flattering the seller. Fixed: the slot covers the first attempt only.
2. The outcome classification counted buyers who only ever got `not_attempted` as "still unknown". But they are *known* not to have bought, which is the whole point of the two kinds of 503.
3. U2 failed on shed 503s as if they were acceptances. The violation is a conflicting user being *given a ticket*. A new test also caught that a leaked ticket on a *retry* would rebind the request_id and hide the leak; fixed.

## Not done / where it still breaks
- Fail-fast is **off by default** (`MAX_INFLIGHT=0`). At 64 it would also shed part of the brief's opening burst (1,000 simultaneous requests); tuning it (or shedding at nginx instead, M8) is an open decision.
- The retry budget lives in *our* buyer. Real browsers pressing F5 have no budget, which is exactly why the seller-side defence matters.
- The limits (64 in flight, 200 retries/s) were chosen by reasoning about capacity (M5), not swept.
