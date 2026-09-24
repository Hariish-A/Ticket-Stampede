"""Fires a schedule at the seller, open-loop, and records one Attempt per request."""

import asyncio
import time
from dataclasses import asdict, dataclass

import aiohttp

from .schedule import Planned


@dataclass(slots=True)
class Attempt:
    kind: str
    user_id: str
    request_id: str
    sched: float  # scheduled send time (perf_counter clock)
    sent: float = 0.0  # when the request was actually handed to the HTTP client
    done: float = 0.0
    status: int = 0  # HTTP status; 0 = no response (timeout / connection error)
    ticket_no: int | None = None
    epoch: int | None = None
    replayed: bool = False
    existing: bool = False
    error: str | None = None

    @property
    def confirmed(self) -> bool:
        """The seller told this buyer, definitively, that they hold ticket_no."""
        return self.status == 200 and self.ticket_no is not None

    def as_dict(self) -> dict:
        return asdict(self)


async def _fire(session: aiohttp.ClientSession, p: Planned, sched: float) -> Attempt:
    a = Attempt(kind=p.kind, user_id=p.user_id, request_id=p.request_id, sched=sched)
    a.sent = time.perf_counter()
    try:
        async with session.post("/buy", json={"user_id": p.user_id, "request_id": p.request_id}) as resp:
            a.status = resp.status
            body = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        a.error = type(exc).__name__
        body = None
    a.done = time.perf_counter()
    if isinstance(body, dict):
        a.ticket_no = body.get("ticket_no")
        a.epoch = body.get("epoch")
        a.replayed = bool(body.get("replayed"))
        a.existing = bool(body.get("existing"))
    return a


async def run_open_loop(target: str, plan: list[Planned], timeout: float, lead: float = 0.5) -> tuple[list[Attempt], float]:
    """Send every planned request at t0 + p.t regardless of outstanding responses.

    Returns the attempts and t0. The connector has no connection limit on
    purpose: a limit would queue requests inside the client, which is exactly
    the closed-loop behaviour this mode exists to avoid.
    """
    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(base_url=target, connector=connector, timeout=client_timeout) as session:
        t0 = time.perf_counter() + lead
        tasks = []
        for p in plan:
            sched = t0 + p.t
            delay = sched - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            tasks.append(asyncio.create_task(_fire(session, p, sched)))
        return list(await asyncio.gather(*tasks)), t0
