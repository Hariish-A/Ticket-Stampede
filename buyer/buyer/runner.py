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
import random
import time
from collections import deque
from dataclasses import asdict, dataclass, replace

import aiohttp

from .schedule import RETRY, Planned


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
    answer: str | None = None  # body "status": purchased / sold_out / unknown / not_attempted / ...
    attempt_no: int = 0  # 0 = first try; n = n-th retry of the same (user, request_id)
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


def retryable(a: Attempt) -> bool:
    """503 (seller has no definite answer) or no response at all (timeout, reset).
    Anything else -- purchased, sold out, conflict -- is a definite answer."""
    return a.status == 503 or a.status == 0


def backoff(n: int, rng: random.Random) -> float:
    """Exponential backoff with jitter: ~0.5, 1, 2, 4, 4 ... seconds, each scaled by
    0.5-1.0 so a stalled crowd does not retry in lock-step."""
    return min(4.0, 0.5 * 2 ** (n - 1)) * rng.uniform(0.5, 1.0)


class RetryBudget:
    """Token bucket capping this process's retries per second; 0 = unlimited.

    Over-budget retries WAIT for a token rather than being dropped, so a buyer
    whose earlier try may have committed still eventually asks again and finds
    out (orphans still get recovered). What the budget prevents is the retry
    storm: M6 measured a 10 s datastore stall becoming a ~2 minute outage when
    every client retried on its own backoff schedule."""

    def __init__(self, rate: float):
        self.rate = rate
        self.tokens = rate
        self.last = time.perf_counter()

    async def take(self) -> None:
        if not self.rate:
            return
        while True:
            now = time.perf_counter()
            self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep((1 - self.tokens) / self.rate)


async def _retry_chain(session: aiohttp.ClientSession, p: Planned, first: Attempt, retries: int,
                       rng: random.Random, budget: RetryBudget | None) -> list[Attempt]:
    """Retry with the SAME request_id while the answer is not definite. Safe because
    the seller is idempotent on request_id: if an earlier try did commit, the retry
    gets that ticket back (replayed=True)."""
    attempts = [first]
    while len(attempts) <= retries and retryable(attempts[-1]):
        await asyncio.sleep(backoff(len(attempts), rng))
        if budget is not None:
            await budget.take()
        a = await _send(session, replace(p, kind=RETRY), sched=None)
        a.attempt_no = len(attempts)
        attempts.append(a)
    return attempts


async def _attempt(session: aiohttp.ClientSession, p: Planned, sched: float | None, retries: int,
                   rng: random.Random, budget: RetryBudget | None = None) -> list[Attempt]:
    return await _retry_chain(session, p, await _send(session, p, sched), retries, rng, budget)


async def _fire(session: aiohttp.ClientSession, p: Planned, sched: float | None,
                slot: asyncio.Semaphore | None = None, retries: int = 0,
                rng: random.Random | None = None, budget: RetryBudget | None = None) -> list[Attempt]:
    # The in-flight slot covers the first attempt only. Holding it through a retry
    # chain's backoff sleeps (the first M6 version) made sleeping retries block
    # *new* sends -- the client throttling its own fresh load, which flatters an
    # overloaded seller. Retries are bounded by the retry budget instead.
    try:
        first = await _send(session, p, sched)
    finally:
        if slot is not None:
            slot.release()
    return await _retry_chain(session, p, first, retries, rng or random.Random(), budget)


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
        a.answer = body.get("status")
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
                        max_inflight: int = 2000, retries: int = 0, retry_rate: float = 0) -> list[Attempt]:
    """Send every planned request at t0 + p.t, regardless of outstanding responses.

    In-flight requests are capped. Without a cap, a client that falls behind
    (because it, or the target, cannot keep up) stops sleeping and floods itself
    with tasks and fresh TCP connections -- in calibration one process spent 7
    minutes and got zero responses that way. With the cap, the scheduler waits
    for a free slot and the request's `sent` time is taken *after* the wait, so
    any backlog shows up as client send lag instead of disappearing.
    """
    slot = asyncio.Semaphore(max_inflight)
    rng = random.Random(os.getpid())
    budget = RetryBudget(retry_rate) if retry_rate else None
    async with _session(target, timeout) as session:
        tasks = []
        for p in plan:
            sched = t0 + p.t
            delay = sched - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await slot.acquire()
            tasks.append(asyncio.create_task(_fire(session, p, sched, slot, retries, rng, budget)))
        return [a for batch in await asyncio.gather(*tasks) for a in batch]


async def run_closed_loop(target: str, plan: list[Planned], t0: float, timeout: float, concurrency: int,
                          deadline: float | None = None, retries: int = 0,
                          retry_rate: float = 0) -> list[Attempt]:
    """`concurrency` loops, each waiting for its response before sending the next request.
    Stops taking new requests at `deadline` (perf_counter) if given."""
    queue = deque(plan)
    out: list[Attempt] = []
    rng = random.Random(os.getpid())
    budget = RetryBudget(retry_rate) if retry_rate else None

    async def loop(session):
        while queue and (deadline is None or time.perf_counter() < deadline):
            out.extend(await _attempt(session, queue.popleft(), None, retries, rng, budget))

    async with _session(target, timeout) as session:
        delay = t0 - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        await asyncio.gather(*(loop(session) for _ in range(max(1, concurrency))))
    return out


def worker_main(target: str, plan: list[Planned], t0: float, timeout: float, concurrency: int | None,
                max_inflight: int = 2000, deadline: float | None = None, retries: int = 0,
                retry_rate: float = 0) -> WorkerResult:
    """Runs in its own process: one event loop, one share of the schedule."""
    cpu0 = time.process_time()
    if concurrency:
        attempts = asyncio.run(run_closed_loop(target, plan, t0, timeout, concurrency, deadline, retries, retry_rate))
    else:
        attempts = asyncio.run(run_open_loop(target, plan, t0, timeout, max_inflight, retries, retry_rate))
    cpu = time.process_time() - cpu0
    start = min((a.sent for a in attempts), default=t0)
    end = max((a.done for a in attempts), default=t0)
    return WorkerResult(attempts, cpu_s=cpu, wall_s=max(end - start, 1e-9), pid=os.getpid())
