"""Fail-fast admission control for /buy (M6).

When more than `limit` /buy requests are already inside the seller, answer the
next one immediately with 503 not_attempted -- before FastAPI routes it,
before Pydantic parses the body, before it waits up to POOL_ACQUIRE_TIMEOUT for
a connection. Without this, an overloaded seller keeps thousands of doomed
requests alive for a second each, spending the CPU it needs to recover (M6
found a 10 s datastore stall turning into a ~2 minute outage).

Pure ASGI, so a rejection costs as little as this process can make it. It is
still per-process Python work: shedding at the edge (nginx) would be cheaper.
"""

REJECT_HEADERS = [(b"content-type", b"application/json"), (b"retry-after", b"1")]
REJECT_BODY = b'{"status":"not_attempted","retry":true,"shed":true}'


class Admission:
    """`stats` is a shared dict (shed count, peak in-flight) exposed on /metrics."""

    def __init__(self, app, limit: int, stats: dict, path: str = "/buy"):
        self.app, self.limit, self.stats, self.path = app, limit, stats, path
        self.inflight = 0

    async def __call__(self, scope, receive, send):
        if not self.limit or scope["type"] != "http" or scope["path"] != self.path:
            return await self.app(scope, receive, send)
        if self.inflight >= self.limit:
            self.stats["admission_shed"] = self.stats.get("admission_shed", 0) + 1
            await send({"type": "http.response.start", "status": 503, "headers": REJECT_HEADERS})
            await send({"type": "http.response.body", "body": REJECT_BODY})
            return
        self.inflight += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.inflight -= 1
