"""Polls /status while the sale is running and checks every snapshot.

Invariant 4 says the count "always" matches the tickets issued. A check after
the run sees only the final state; a count that disagreed with the list for a
moment mid-sale, or a confirmed sale that vanished and came back, would pass.
Each snapshot is checked on its own, and consecutive snapshots against each
other (within one sale, tickets are only ever added).
"""

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field

import aiohttp

MAX_EXAMPLES = 5


@dataclass
class AuditResult:
    snapshots: int = 0
    failed_polls: int = 0
    violations: Counter = field(default_factory=Counter)
    examples: list = field(default_factory=list)
    duration_s: float = 0.0

    def record(self, kind: str, t: float, **detail) -> None:
        self.violations[kind] += 1
        if len(self.examples) < MAX_EXAMPLES:
            self.examples.append({"kind": kind, "t_s": round(t, 3), **detail})


def check_snapshot(s: dict, total: int, prev: dict | None, result: AuditResult, t: float) -> None:
    holders = s.get("holders", [])
    sold = s.get("sold")
    tickets = [h["ticket_no"] for h in holders]
    users = [h["user_id"] for h in holders]
    if sold != len(holders):
        result.record("count_mismatch", t, sold=sold, holders=len(holders))
    if (sold or 0) > total or len(holders) > total:
        result.record("oversell", t, sold=sold, holders=len(holders), total=total)
    if len(set(tickets)) != len(tickets):
        result.record("duplicate_ticket", t, repeated=len(tickets) - len(set(tickets)))
    if len(set(users)) != len(users):
        result.record("user_holds_two", t, repeated=len(users) - len(set(users)))
    if prev is not None and prev.get("epoch") == s.get("epoch"):
        before = {(h["user_id"], h["ticket_no"]) for h in prev.get("holders", [])}
        now = {(h["user_id"], h["ticket_no"]) for h in holders}
        vanished = before - now
        if vanished:
            result.record("sale_vanished", t, vanished=sorted(vanished)[:3])
        if (sold or 0) < (prev.get("sold") or 0):
            result.record("count_decreased", t, before=prev.get("sold"), after=sold)


async def audit(target: str, total: int, stop: asyncio.Event, interval: float) -> AuditResult:
    result = AuditResult()
    start = time.perf_counter()
    prev = None
    async with aiohttp.ClientSession(base_url=target, timeout=aiohttp.ClientTimeout(total=5)) as session:
        while not stop.is_set():
            try:
                async with session.get("/status") as resp:
                    body = await resp.json(content_type=None)
                ok = resp.status == 200 and isinstance(body, dict)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                ok = False
            if ok:
                result.snapshots += 1
                check_snapshot(body, total, prev, result, time.perf_counter() - start)
                prev = body
            else:
                result.failed_polls += 1  # a slow/unavailable /status is not itself a violation
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    result.duration_s = time.perf_counter() - start
    return result
