# M8 / TF1: three seller instances behind a load balancer, no application-level lock

**Topology** (`TOPOLOGY=tf1`, `scripts/tf1.sh`):
- The buyer talks to nginx (`least_conn`, keep-alive to the upstreams).
- nginx routes to seller1–3: identical, stateless FastAPI processes, **sharing nothing but Postgres**. There is no lock, leader, sticky session or coordination between them.
- Every invariant rests on the Postgres constraints (ticket PK, UNIQUE request_id, UNIQUE user_id) and single-statement claims. So which instance a request, its duplicate, or its retry lands on cannot matter, and the runs below test exactly that.
- nginx does not resend a POST to another seller once sent (explicit `proxy_next_upstream error timeout`, no `non_idempotent`).

## Correctness: every scenario rerun through the load balancer

| scenario | result |
|---|---|
| [C1: naive](20260924T180741Z-c1-naive-tf1/report.md) | FAIL, as it must: **8,580 tickets for 100 seats** (≈2,000 on one instance). Three processes racing on one read-then-write interleave more. That's why TF1 is "a different problem": single-process accidents don't carry over. |
| [C1: skiplocked](20260924T180846Z-c1-skiplocked-tf1/report.md) | **all PASS** (I1–I4, U1–U5, live audit 0 violations / 494 snapshots). Concurrent twins, duplicates and replays spread over 3 instances. |
| [Kill Postgres mid-sale](20260924T181945Z-killdb-tf1-summary.md) | normal run: **all PASS, 0 phantoms**; 7 in-flight purchases had committed and were recovered by retry. Control (`synchronous_commit=off`): **FAIL, as it must** (2 confirmed sales lost and resold, caught only by the buyer's ledger). |
| [Postgres +3 s for 10 s](20260924T182315Z-slowdb-tf1-summary.md) | invariants PASS in both variants. Baseline: the same retry storm as with one instance (560 orphans, 3,440 never answered): 3× the capacity doesn't prevent the storm, it only takes a bigger one. Retry budget + fail-fast: **0 orphans, 0 unanswered**. |

## Throughput: 3 instances scale ~1.3× on this laptop, and we know why

[3-instance sweep](20260924T180951Z-sweep-tf1/summary.md) (8 client processes) vs [1 instance, M5](20260924T092512Z-sweep/summary.md):

| | 1 instance (direct) | 3 instances (nginx) |
|---|---|---|
| p99 at 1,000 req/s | 15 ms | 18 ms |
| knee | ~1,500 req/s | **~2,000 req/s** (p99 18 → 630 ms between 1,000 and 2,000) |
| seller CPU per request at the knee | ~0.57 ms | **~1.17 ms** |

Past the knee the rows are overload behaviour (the client's in-flight cap binds; send lag grows to seconds). They are not read as capacity.

**Why only 1.3×.** Three hypotheses, each tested:
1. **Uneven balancing: ruled out.** Per-instance CPU at 1,000 req/s was 48 / 50 / 46%, and at 2,000 it was 78 / 76 / 79%.
2. **Connection churn nginx → seller** (a broken keep-alive would cost each Python seller an accept and protocol setup per request): **ruled out.** Under 1,500 req/s nginx held ~86 ESTABLISHED connections to the sellers and 2 in TIME_WAIT.
3. **Shared-host contention: measured.** Everything runs on one **8-core / 16-thread Ryzen 7 7435HS**: the load generator, 3 sellers, Postgres and nginx. At the knee they use ~6.3 logical CPUs, ~3 of them the client. At the same 1,500 req/s through the same 3 sellers, changing *only* the client's process count ([2](20260924T181435Z-sweep-tf1/summary.md) vs [8](20260924T181526Z-sweep-tf1/summary.md)) moved seller CPU per request from **0.95 ms to 1.19 ms (+25%)**. A busier client makes every seller slower. With 2 client processes, a seller behind nginx costs about what a single direct seller costs at a similar per-instance rate, so nginx itself adds little.

**Conclusion.** The design scales horizontally in *correctness* (proved above). The *throughput* number on one laptop is bounded by the laptop. A clean scaling curve needs the client, the sellers and Postgres on separate machines, which is what the deferred AWS step would buy. Also, each Python instance still hits its knee near ~80% CPU (queueing at one event loop), so a per-instance ceiling of roughly 700–1,500 req/s depends on how much of the core it really gets.

## Also checked
- **nginx resolves the seller hostnames once, at startup**, so a seller recreated on a new IP would be unreachable. I tried to reproduce it: Docker gave the recreated seller2 the same IP, and 60/60 requests succeeded. The scripts restart nginx after recreating sellers anyway (cheap insurance); the compose comment states what was actually observed.
- **The scripts are now topology-parametrised** (`scripts/lib.sh`: `TOPOLOGY=single|tf1`), so every M1–M7 experiment runs unchanged against the three-instance setup.

## Limits
- **nginx is a single point of failure**, as is the single Postgres node.
- **Fail-fast (`MAX_INFLIGHT`) is per instance.** With 3 instances, the effective limit is 3 × 64. D24 is still open.
- **The throughput comparison is machine-bound** (see above).
