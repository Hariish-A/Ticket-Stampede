import asyncio
import logging
import time
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import allocators, config, db, sale
from .admission import Admission
from .allocators.constrained import RetriesExhausted
from .sale import Purchased, RequestIdConflict, SoldOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("seller")

settings = config.load()

# Anything that means "the datastore did not give us a definite answer".
DB_ERRORS = (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, asyncio.TimeoutError, RetriesExhausted)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.allocator = allocators.get(settings.allocator)
    app.state.pool = await db.create_pool(settings)
    await db.apply_schema(app.state.pool)
    log.info("seller ready: allocator=%s pool=%d..%d", settings.allocator, settings.pool_min, settings.pool_max)
    yield
    await app.state.pool.close()


app = FastAPI(title="Ticket Stampede seller", lifespan=lifespan)
admission_stats: dict = {}
app.add_middleware(Admission, limit=settings.max_inflight, stats=admission_stats)


class ResetIn(BaseModel):
    count: int = Field(ge=0, le=1_000_000)


class BuyIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)


def unknown_outcome() -> JSONResponse:
    # A query was sent and no answer came back: the purchase may or may not have
    # committed. Saying "sold out" or "failed" here could be a lie; the
    # request_id makes a retry safe, and the retry will find it if it committed.
    return JSONResponse(
        status_code=503,
        content={"status": "unknown", "retry_with_same_request_id": True},
        headers={"Retry-After": "1"},
    )


def not_attempted() -> JSONResponse:
    # No database connection was obtained, so nothing was sent: the outcome is
    # known -- nothing happened. Still a 503 (retry later), but a client can
    # tell "definitely not bought" apart from "maybe bought".
    return JSONResponse(
        status_code=503,
        content={"status": "not_attempted", "retry": True},
        headers={"Retry-After": "1"},
    )


_failures = 0


def log_failure(what: str, exc: BaseException) -> None:
    """A stalled datastore fails thousands of requests a second; logging each
    would spend the CPU that M5 showed is the bottleneck. Log the first 20,
    then 1 in 500."""
    global _failures
    _failures += 1
    if _failures <= 20 or _failures % 500 == 0:
        log.warning("%s failed (#%d): %r", what, _failures, exc)


@app.get("/health")
async def health():
    return {"ok": True, "allocator": settings.allocator}


@app.get("/metrics")
async def metrics():
    """What the allocator had to do (retries, fallbacks), since this process started.
    The buyer reads it before and after a run and reports the difference."""
    return {"allocator": settings.allocator, "max_inflight": settings.max_inflight,
            "counters": {**app.state.allocator.counters, **admission_stats}}


@app.post("/reset")
async def reset(body: ResetIn):
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            epoch = await sale.reset(conn, body.count)
    except DB_ERRORS as exc:
        log_failure("reset", exc)
        return unknown_outcome()
    return {"status": "reset", "epoch": epoch, "total": body.count, "allocator": settings.allocator}


def server_timing(start: float, acquired: float | None, allocated: float | None) -> dict:
    """Server-Timing header: where this request's time went inside the handler.
    acq = waiting for a pool connection; alloc = the allocator's queries (incl.
    asyncpg overhead); handler = all of it. The buyer subtracts `handler` from
    the latency it measured: the rest was spent outside the handler (HTTP
    parsing, queueing for the event loop, network) -- the part that grows when
    this process runs out of CPU."""
    now = time.perf_counter()
    parts = []
    if acquired is not None:
        parts.append(f"acq;dur={(acquired - start) * 1000:.2f}")
        if allocated is not None:
            parts.append(f"alloc;dur={(allocated - acquired) * 1000:.2f}")
    parts.append(f"handler;dur={(now - start) * 1000:.2f}")
    return {"Server-Timing": ", ".join(parts)}


@app.post("/buy")
async def buy(body: BuyIn):
    start = time.perf_counter()
    acquired = allocated = None
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            acquired = time.perf_counter()
            result = await app.state.allocator.buy(conn, body.user_id, body.request_id)
            allocated = time.perf_counter()
    except DB_ERRORS as exc:
        log_failure("buy", exc)
        if allocated is None:
            # Which 503 depends on how far we got: no connection means nothing
            # was sent (known: not bought); a connection means a statement may
            # have committed without us hearing back (unknown).
            resp = not_attempted() if acquired is None else unknown_outcome()
            resp.headers.update(server_timing(start, acquired, allocated))
            return resp
        # The allocator already returned a definite result and only releasing the
        # connection failed: the answer is known, so give it rather than a 503.

    match result:
        case Purchased():
            code, content = 200, {
                "status": "purchased",
                "ticket_no": result.ticket_no,
                "epoch": result.epoch,
                "replayed": result.replayed,
                "existing": result.existing,
            }
        case SoldOut():
            code, content = 409, {"status": "sold_out", "epoch": result.epoch}
        case RequestIdConflict():
            code, content = 422, {"status": "request_id_conflict",
                                  "detail": "request_id already used by another user_id"}
    return JSONResponse(status_code=code, content=content, headers=server_timing(start, acquired, allocated))


@app.get("/status")
async def status():
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            snapshot = await app.state.allocator.status(conn)
    except DB_ERRORS as exc:
        log_failure("status", exc)
        return unknown_outcome()
    return {**snapshot, "allocator": settings.allocator}
