"""Fires requests at the seller and records one Attempt per request.

Two modes:
  open-loop   (default) each request is sent at its scheduled time whether or
              not earlier ones have been answered. Latency counts from the
              scheduled time, so a stall is measured, not hidden.
  closed-loop (--concurrency C) C loops, each sending its next request only
              after the previous one returns. Kept for the C4 comparison: when
              the seller stalls, this client politely stops sending and the
              stall mostly vanishes from its numbers (coordinated omission).

`worker_main` is the entry point of each worker process.
"""

import asyncio
import os
import time
from collections import deque
from dataclasses import asdict, dataclass

import aiohttp

from .schedule import Planned


@dataclass(slots=True)
class Attempt:
    kind: str
    user_id: str
    request_id: str
    sched: float  # scheduled send time (perf_counter clock; shared across processes on one host)
    sent: float = 0.0  # when the request was actually handed to the HTTP client
    done: float = 0.0
    status: int = 0  # HTTP status; 0 = no response (timeout / connection error)
    ticket_no: int | None = None
    epoch: int | None = None
    replayed: bool = False
    existing: bool = False
    error: str | None = None
    # From the seller's Server-Timing header (ms): pool wait, allocator queries, whole handler.
    srv_acq: float | None = None
    srv_alloc: float | None = None
    srv_handler: float | None = None

    @property
    def confirmed(self) -> bool:
        """The seller told this buyer, definitively, that they hold ticket_no."""
        return self.status == 200 and self.ticket_no is not None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkerResult:
    attempts: list[Attempt]
    cpu_s: float  # CPU time this worker process consumed
    wall_s: float  # wall time from start of sending to last response
    pid: int

    @property
    def cpu_util(self) -> float:
        """Fraction of one core. Close to 1.0 means this worker, not the target, was the limit."""
        return self.cpu_s / self.wall_s if self.wall_s > 0 else 0.0


async def _fire(session: aiohttp.ClientSession, p: Planned, sched: float | None,
                slot: asyncio.Semaphore | None = None) -> Attempt:
    try:
        return await _send(session, p, sched)
    finally:
        if slot is not None:
            slot.release()


async def _send(session: aiohttp.ClientSession, p: Planned, sched: float | None) -> Attempt:
    sent = time.perf_counter()
    a = Attempt(kind=p.kind, user_id=p.user_id, request_id=p.request_id, sched=sent if sched is None else sched, sent=sent)
    try:
        async with session.post("/buy", json={"user_id": p.user_id, "request_id": p.request_id}) as resp:
            a.status = resp.status
            timing = parse_server_timing(resp.headers.get("Server-Timing"))
            a.srv_acq, a.srv_alloc, a.srv_handler = timing.get("acq"), timing.get("alloc"), timing.get("handler")
            body = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as exc:
        a.error = type(exc).__name__
        body = None
    a.done = time.perf_counter()
    if isinstance(body, dict):
        a.ticket_no = body.get("ticket_no")
        a.epoch = body.get("epoch")
        a.replayed = bool(body.get("replayed"))
        a.existing = bool(body.get("existing"))
    return a


def parse_server_timing(header: str | None) -> dict[str, float]:
    """'acq;dur=0.08, alloc;dur=2.47' -> {'acq': 0.08, 'alloc': 2.47}. Unknown/malformed parts are skipped."""
    out: dict[str, float] = {}
    for part in (header or "").split(","):
        name, _, rest = part.strip().partition(";")
        for param in rest.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "dur" and name:
                try:
                    out[name] = float(value)
                except ValueError:
                    pass
    return out


def _session(target: str, timeout: float) -> aiohttp.ClientSession:
    # No connector limit: in-flight requests are bounded by our own semaphore
    # instead, so that any wait is recorded as client send lag (see run_open_loop).
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    return aiohttp.ClientSession(base_url=target, connector=connector, timeout=aiohttp.ClientTimeout(total=timeout))


async def run_open_loop(target: str, plan: list[Planned], t0: float, timeout: float,
                        max_inflight: int = 2000) -> list[Attempt]:
    """Send every planned request at t0 + p.t, regardless of outstanding responses.

    In-flight requests are capped. Without a cap, a client that falls behind
    (because it, or the target, cannot keep up) stops sleeping and floods itself
    with tasks and fresh TCP connections -- in calibration one process spent 7
    minutes and got zero responses that way. With the cap, the scheduler waits
    for a free slot and the request's `sent` time is taken *after* the wait, so
    any backlog shows up as client send lag instead of disappearing.
    """
    slot = asyncio.Semaphore(max_inflight)
    async with _session(target, timeout) as session:
        tasks = []
        for p in plan:
            sched = t0 + p.t
            delay = sched - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await slot.acquire()
            tasks.append(asyncio.create_task(_fire(session, p, sched, slot)))
        return list(await asyncio.gather(*tasks))


async def run_closed_loop(target: str, plan: list[Planned], t0: float, timeout: float, concurrency: int,
                          deadline: float | None = None) -> list[Attempt]:
    """`concurrency` loops, each waiting for its response before sending the next request.
    Stops taking new requests at `deadline` (perf_counter) if given."""
    queue = deque(plan)
    out: list[Attempt] = []

    async def loop(session):
        while queue and (deadline is None or time.perf_counter() < deadline):
            out.append(await _send(session, queue.popleft(), sched=None))

    async with _session(target, timeout) as session:
        delay = t0 - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        await asyncio.gather(*(loop(session) for _ in range(max(1, concurrency))))
    return out


def worker_main(target: str, plan: list[Planned], t0: float, timeout: float, concurrency: int | None,
                max_inflight: int = 2000, deadline: float | None = None) -> WorkerResult:
    """Runs in its own process: one event loop, one share of the schedule."""
    cpu0 = time.process_time()
    if concurrency:
        attempts = asyncio.run(run_closed_loop(target, plan, t0, timeout, concurrency, deadline))
    else:
        attempts = asyncio.run(run_open_loop(target, plan, t0, timeout, max_inflight))
    cpu = time.process_time() - cpu0
    start = min((a.sent for a in attempts), default=t0)
    end = max((a.done for a in attempts), default=t0)
    return WorkerResult(attempts, cpu_s=cpu, wall_s=max(end - start, 1e-9), pid=os.getpid())
