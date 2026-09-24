# M7 / TF2: kill the datastore in the middle of the sale and bring it back

**Setup** (`scripts/killdb.sh`):
- **Sale:** 15,000 tickets for 40,000 buyers (1,000 at t=0, then 1,000/s). The kill must land while tickets are still selling; with 100 tickets the sale is over in about 0.1 s.
- **Kill:** Postgres gets **SIGKILL** mid-sale (no shutdown, no checkpoint; the postmaster and every backend die mid-statement). It's started again 5 s later and runs crash recovery (`database system was not properly shut down; automatic recovery in progress … redo done`).
- **Buyers:** they retry unclear answers (any 5xx, or no response) with the **same request_id**, up to 10 times, under a 200 retries/s budget (M6).
- **Timestamps:** kill and recovery times are recorded on the Docker VM clock, the same clock as the buyer, and placed on its timeline. [Summary table](20260924T175318Z-killdb-summary.md).

## Result: 3 out of 3 runs keep every invariant, and no confirmed sale is lost

| run | killed at | Postgres healthy again | in flight at the kill: **had committed** / had not | invariants | confirmed to buyers vs in `/status` | phantoms (lost sales) | orphans |
|---|---|---|---|---|---|---|---|
| [1](20260924T173849Z-killdb-1/report.md) | t=5.5 s | t=25.1 s | **30** / 243 (+1,058 later sold out) | all PASS | 15,000 = 15,000 | **0** | 0 |
| [2](20260924T174224Z-killdb-2/report.md) | t=7.1 s | t=16.1 s | **15** / 125 (+1,097) | all PASS | 15,000 = 15,000 | **0** | 0 |
| [3](20260924T174602Z-killdb-3/report.md) | t=9.7 s | t=20.4 s | **32** / 336 (+1,220) | all PASS | 15,000 = 15,000 | **0** | 0 |
| [control: `synchronous_commit=off`](20260924T175008Z-killdb-off/report.md) | t=7.2 s | t=17.3 s | 4 / 40 (+635) | **FAIL: I1, I2, I4** | **15,006** confirmed vs 15,000 | **6** | 0 |

"In flight at the kill" means sent before the kill and answered after it. The report follows each one:
- **Had committed:** the retry found the ticket as a replay. The commit survived the crash, but the seller never got to say so; the same-request_id retry recovered it.
- **Had not:** the retry bought a ticket afresh. The statement died with Postgres and left nothing behind.

This is the evidence that the kill landed *during* commits, not between them.

## Why no confirmed sale can be lost (the durability argument)
1. **Confirmation only follows a durable commit.** The seller answers 200 only after the claim's `UPDATE` has *returned*. In autocommit, that happens only after Postgres has committed it, and with `synchronous_commit=on` (set explicitly in compose) a commit is acknowledged only once its WAL record has been flushed. Crash recovery replays the WAL, so every acknowledged commit is back after restart.
2. **Anything else is not a confirmation.** A buyer whose statement was cut off gets 503 `unknown` (or no response), never a ticket number. So the set of confirmed tickets is always a subset of what the WAL made durable.
3. **The ambiguous middle** (committed, but the acknowledgement was lost with the process) is exactly the "had committed" row above. It is resolved by idempotency: the same request_id finds the row.
4. **No duplicate ticket numbers after recovery.** Replay restores exactly the committed rows, and the constraints (PK on ticket_no, UNIQUE on request_id and user_id) hold for the recovered data as for any other. No application state survives the crash that could disagree with it: the sellers keep none (the seller restarted nothing; its pool reconnected).

## The control run: proof that the harness can see a lost sale
With `synchronous_commit=off`, Postgres acknowledges a commit *before* flushing its WAL. That is the one setting that breaks step 1. The same kill then:
- **lost 6 sales that had been confirmed to buyers.** Their commits were acknowledged and gone after recovery (I4: phantoms);
- **resold those 6 ticket numbers to other buyers**, because the rows were unsold again after recovery (I2: 6 ticket numbers confirmed to two different users; I1: 15,006 confirmations for 15,000 seats).

**`/status` after the restart looked perfect**: 15,000 sold, no duplicates, count equal to the list, and the live audit (A3) passed. The damage is invisible from the seller's side. It was caught only because the buyer keeps its own ledger of every confirmation and reconciles it against `/status` (decided in Session 2). A harness that verified the invariants "by reading /status", as the brief puts it, would have passed this run. Without this control, "0 phantoms" in runs 1–3 would only mean the check never fired. With it, we know the check works.

## Bugs found by the first kill trial (fixed, run discarded)
- **The seller answered HTTP 500 to 4 buyers.** asyncpg raised `InternalClientError` while *releasing* a connection the kill had broken. That type was not in the seller's list of database errors, so it escaped as a 500. **Fix:** `/buy` never answers 500. Whatever the exception, the answer depends on how far the request got: the result if the allocator already returned one, `unknown` if a statement may have been sent, `not_attempted` if not.
- **The buyer treated that 500 as a final answer** and stopped retrying, leaving 2 buyers holding tickets they were never told about. **Fix:** any 5xx is unclear and retried.
- **Lesson:** listing the exceptions I knew about was the wrong design. The rule "never turn an unknown into a definite answer" has to be structural, not a list of types.

## Also verified
- `restart: unless-stopped` does **not** auto-restart a `docker kill`ed Postgres (0 restarts in 6 s). The downtime in these runs is controlled by the script. (Open question from M3.)
- The seller needs no restart. Its pool drops the broken connections and reconnects once Postgres is healthy.

## Limits (not claimed)
- **`docker kill` is a process crash, not a power cut.** WAL already handed to the kernel survives a process crash even if it was never fsynced. So this demonstrates crash safety of the *process*. Power-loss durability depends on the disk honouring fsync, which Docker Desktop's virtual disk makes impossible to test here. `synchronous_commit=off` lost data because unflushed WAL sat in Postgres's *own* shared memory, which dies with the process.
- **Recovery took 9–20 s from kill to healthy** (5 s of that is deliberate downtime). During it, buyers got 503s and retried, and the sale sold out at 49–85 s instead of about 15 s. Correct, but slow.
- **A buyer who gives up before the database returns keeps an orphan they don't know about.** Every buyer here eventually retried (0 orphans), but only because the retry limit and budget outlast the outage.
- **Single Postgres node:** there is no failover, so the sale is down while Postgres is. With asynchronous replication, failover would reintroduce exactly the control run's losses.
