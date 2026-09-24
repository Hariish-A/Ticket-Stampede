"""Fault injection driven by the buyer itself, on the same clock as its schedule.

The buyer knows exactly when its t0 is, so it -- not a shell script sleeping
"about 5 seconds" -- switches the fault on and off. The report's timeline and
the fault window then line up to the millisecond.

Uses toxiproxy (compose service `toxiproxy`, proxy `postgres`): a `latency`
toxic on the downstream stream delays every byte Postgres sends back. Queries
still reach Postgres and still commit on time; only the answers are late. That
is the nasty version of "the datastore goes slow": work gets done that the
seller never hears about.
"""

import asyncio
import time
from dataclasses import dataclass

import aiohttp

TOXIC = "stall"


@dataclass
class FaultWindow:
    kind: str
    planned_start_s: float  # relative to t0
    planned_end_s: float
    actual_start_s: float | None = None
    actual_end_s: float | None = None
    detail: str = ""
    error: str | None = None


def external_window(path: str, t0_wall: float, wait_s: float = 30.0) -> FaultWindow | None:
    """A fault driven from outside the buyer (e.g. `docker kill`, which needs the
    host's Docker CLI). The script records wall-clock times on the container clock
    -- the same clock as t0_wall -- as {"kind", "detail", "events": {name: epoch_s}}
    with events "fault" (start) and "recovered" (end)."""
    import json
    import os

    deadline = time.monotonic() + wait_s
    while not os.path.exists(path):
        if time.monotonic() > deadline:
            return None
        time.sleep(0.5)
    time.sleep(0.2)  # let the writer finish
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    ev = d.get("events", {})
    rel = {k: round(v - t0_wall, 3) for k, v in ev.items()}
    return FaultWindow(d.get("kind", "external"), rel.get("fault"), rel.get("recovered"),
                       actual_start_s=rel.get("fault"), actual_end_s=rel.get("recovered"),
                       detail=d.get("detail", "") + f" (events relative to t0: {rel})")


async def latency_window(api: str, proxy: str, t0: float, start_s: float, duration_s: float,
                         latency_ms: int) -> FaultWindow:
    w = FaultWindow("latency", start_s, start_s + duration_s,
                    detail=f"+{latency_ms} ms on every response from Postgres (toxiproxy '{proxy}')")
    toxic = {"name": TOXIC, "type": "latency", "stream": "downstream", "toxicity": 1.0,
             "attributes": {"latency": latency_ms, "jitter": 0}}
    async with aiohttp.ClientSession(base_url=api, timeout=aiohttp.ClientTimeout(total=5)) as s:
        # Clear a toxic left behind by an interrupted earlier run.
        async with s.delete(f"/proxies/{proxy}/toxics/{TOXIC}"):
            pass
        try:
            await asyncio.sleep(max(0.0, t0 + start_s - time.perf_counter()))
            async with s.post(f"/proxies/{proxy}/toxics", json=toxic) as r:
                if r.status >= 300:
                    w.error = f"add toxic: HTTP {r.status} {await r.text()}"
                    return w
            w.actual_start_s = time.perf_counter() - t0
            await asyncio.sleep(max(0.0, t0 + start_s + duration_s - time.perf_counter()))
        finally:
            async with s.delete(f"/proxies/{proxy}/toxics/{TOXIC}") as r:
                if w.actual_start_s is not None:
                    w.actual_end_s = time.perf_counter() - t0
                if r.status >= 300 and r.status != 404:
                    w.error = f"remove toxic: HTTP {r.status}"
    return w
