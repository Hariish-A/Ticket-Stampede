import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import allocators, config, db, sale
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


class ResetIn(BaseModel):
    count: int = Field(ge=0, le=1_000_000)


class BuyIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)


def unknown_outcome() -> JSONResponse:
    # We cannot tell whether the purchase committed. Saying "sold out" or
    # "failed" here could be a lie; the request_id makes a retry safe.
    return JSONResponse(
        status_code=503,
        content={"status": "unknown", "retry_with_same_request_id": True},
        headers={"Retry-After": "1"},
    )


@app.get("/health")
async def health():
    return {"ok": True, "allocator": settings.allocator}


@app.get("/metrics")
async def metrics():
    """What the allocator had to do (retries, fallbacks), since this process started.
    The buyer reads it before and after a run and reports the difference."""
    return {"allocator": settings.allocator, "counters": dict(app.state.allocator.counters)}


@app.post("/reset")
async def reset(body: ResetIn):
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            epoch = await sale.reset(conn, body.count)
    except DB_ERRORS as exc:
        log.warning("reset failed: %r", exc)
        return unknown_outcome()
    return {"status": "reset", "epoch": epoch, "total": body.count, "allocator": settings.allocator}


@app.post("/buy")
async def buy(body: BuyIn):
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            result = await app.state.allocator.buy(conn, body.user_id, body.request_id)
    except DB_ERRORS as exc:
        log.warning("buy failed: %r", exc)
        return unknown_outcome()

    match result:
        case Purchased():
            return {
                "status": "purchased",
                "ticket_no": result.ticket_no,
                "epoch": result.epoch,
                "replayed": result.replayed,
                "existing": result.existing,
            }
        case SoldOut():
            return JSONResponse(status_code=409, content={"status": "sold_out", "epoch": result.epoch})
        case RequestIdConflict():
            return JSONResponse(
                status_code=422,
                content={"status": "request_id_conflict", "detail": "request_id already used by another user_id"},
            )


@app.get("/status")
async def status():
    try:
        async with app.state.pool.acquire(timeout=settings.pool_acquire_timeout) as conn:
            snapshot = await app.state.allocator.status(conn)
    except DB_ERRORS as exc:
        log.warning("status failed: %r", exc)
        return unknown_outcome()
    return {**snapshot, "allocator": settings.allocator}
