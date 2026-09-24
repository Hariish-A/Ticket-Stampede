"""Splits a schedule across worker processes and runs them against one start time.

One Python process tops out at a few thousand requests/s (M1 showed a single
process falling up to 310 ms behind schedule during a 1,000-request burst).
Each worker owns every P-th request, so a burst at t=0 is spread evenly and all
workers aim at the same absolute instants. perf_counter is CLOCK_MONOTONIC on
Linux, which is system-wide, so t0 means the same moment in every process.
"""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

from .runner import Attempt, WorkerResult, worker_main
from .schedule import Planned

SPAWN_LEAD_S = 2.0  # time for worker processes to start and import before t0


async def run_phase(target: str, plan: list[Planned], processes: int, timeout: float,
                    concurrency: int | None = None, max_inflight: int = 2000,
                    duration: float | None = None) -> tuple[list[Attempt], list[WorkerResult], float]:
    """Returns (attempts, per-worker results, t0). Must be awaited from the coordinator's loop,
    which stays free to run the live auditor while the workers fire."""
    processes = max(1, processes)
    shards = [plan[i::processes] for i in range(processes)]
    per_worker_conc = -(-concurrency // processes) if concurrency else None
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=processes, mp_context=get_context("spawn")) as pool:
        t0 = time.perf_counter() + SPAWN_LEAD_S
        deadline = t0 + duration if duration else None
        futures = [loop.run_in_executor(pool, worker_main, target, shard, t0, timeout, per_worker_conc,
                                        max_inflight, deadline)
                   for shard in shards if shard]
        results: list[WorkerResult] = list(await asyncio.gather(*futures))
    attempts = [a for r in results for a in r.attempts]
    return attempts, results, t0
