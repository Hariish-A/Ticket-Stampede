"""Integration tests: the safe allocators against a real Postgres, with real
concurrency (many connections, asyncio.gather). Each test targets one race."""

import asyncio
import os

import asyncpg
import pytest

from app import db, sale
from app.allocators import get
from app.sale import Purchased, RequestIdConflict, SoldOut

SAFE = ["skiplocked", "counter", "serializable"]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=60)
    await db.apply_schema(p)
    yield p
    await p.close()


async def reset(pool, n):
    async with pool.acquire() as conn:
        return await sale.reset(conn, n)


async def buy(pool, alloc, user, rid):
    async with pool.acquire() as conn:
        return await alloc.buy(conn, user, rid)


async def status(pool, alloc):
    async with pool.acquire() as conn:
        return await alloc.status(conn)


@pytest.mark.parametrize("name", SAFE)
async def test_sells_exactly_n_under_contention(pool, name):
    alloc = get(name)
    await reset(pool, 20)
    results = await asyncio.gather(*(buy(pool, alloc, f"u{i}", f"r{i}") for i in range(300)))
    won = [r for r in results if isinstance(r, Purchased)]
    assert len(won) == 20
    assert sorted(r.ticket_no for r in won) == list(range(1, 21))
    assert sum(isinstance(r, SoldOut) for r in results) == 280
    s = await status(pool, alloc)
    assert s["sold"] == len(s["holders"]) == 20


@pytest.mark.parametrize("name", SAFE)
async def test_concurrent_twins_share_one_ticket(pool, name):
    alloc = get(name)
    await reset(pool, 10)
    results = await asyncio.gather(*(buy(pool, alloc, "alice", "r1") for _ in range(25)))
    assert all(isinstance(r, Purchased) for r in results)
    assert len({r.ticket_no for r in results}) == 1
    assert sum(not r.replayed for r in results) == 1  # exactly one request actually bought
    s = await status(pool, alloc)
    assert s["sold"] == 1


@pytest.mark.parametrize("name", SAFE)
async def test_same_user_many_request_ids_gets_one_ticket(pool, name):
    alloc = get(name)
    await reset(pool, 10)
    results = await asyncio.gather(*(buy(pool, alloc, "bob", f"r{i}") for i in range(25)))
    assert len({r.ticket_no for r in results}) == 1
    assert sum(not (r.replayed or r.existing) for r in results) == 1
    assert (await status(pool, alloc))["sold"] == 1


@pytest.mark.parametrize("name", SAFE)
async def test_request_id_reused_by_other_user_is_rejected(pool, name):
    alloc = get(name)
    await reset(pool, 10)
    assert isinstance(await buy(pool, alloc, "alice", "r1"), Purchased)
    assert isinstance(await buy(pool, alloc, "mallory", "r1"), RequestIdConflict)


@pytest.mark.parametrize("name", SAFE)
async def test_request_id_conflict_race_has_exactly_one_winner(pool, name):
    alloc = get(name)
    await reset(pool, 10)
    results = await asyncio.gather(*(buy(pool, alloc, f"user{i}", "shared") for i in range(20)))
    assert sum(isinstance(r, Purchased) for r in results) == 1
    assert sum(isinstance(r, RequestIdConflict) for r in results) == 19


@pytest.mark.parametrize("name", SAFE)
async def test_winner_replay_after_sellout_gets_their_ticket(pool, name):
    alloc = get(name)
    await reset(pool, 2)
    first = await buy(pool, alloc, "a", "ra")
    await buy(pool, alloc, "b", "rb")
    assert isinstance(await buy(pool, alloc, "c", "rc"), SoldOut)
    replay = await buy(pool, alloc, "a", "ra")
    assert isinstance(replay, Purchased) and replay.replayed and replay.ticket_no == first.ticket_no
    again = await buy(pool, alloc, "a", "ra-retry")  # D7: new request_id, same user
    assert isinstance(again, Purchased) and again.existing and again.ticket_no == first.ticket_no


@pytest.mark.parametrize("name", SAFE)
async def test_no_false_sold_out_while_last_ticket_is_mid_claim(pool, name):
    """The SKIP LOCKED trap: the only unsold row is locked by a claim that then
    rolls back. The buyer must wait and get the ticket, not be told 'sold out'."""
    alloc = get(name)
    await reset(pool, 1)
    async with pool.acquire() as holder:
        tx = holder.transaction()
        await tx.start()
        await holder.execute("SELECT 1 FROM tickets WHERE ticket_no = 1 FOR UPDATE")
        pending = asyncio.create_task(buy(pool, alloc, "patient", "rp"))
        await asyncio.sleep(0.3)
        assert not pending.done(), "buyer answered while the last ticket was still undecided"
        await tx.rollback()
    result = await asyncio.wait_for(pending, 5)
    assert isinstance(result, Purchased) and result.ticket_no == 1


@pytest.mark.parametrize("name", SAFE)
async def test_sold_out_once_mid_claim_ticket_commits(pool, name):
    alloc = get(name)
    await reset(pool, 1)
    async with pool.acquire() as holder:
        tx = holder.transaction()
        await tx.start()
        await holder.execute(
            "UPDATE tickets SET user_id='early', request_id='re', sold_at=now() WHERE ticket_no = 1")
        pending = asyncio.create_task(buy(pool, alloc, "late", "rl"))
        await asyncio.sleep(0.3)
        assert not pending.done()
        await tx.commit()
    assert isinstance(await asyncio.wait_for(pending, 5), SoldOut)


@pytest.mark.parametrize("name", SAFE)
async def test_database_rejects_a_double_sale_even_if_code_tried(pool, name):
    """Defence in depth: the constraints hold even against a buggy writer."""
    await reset(pool, 3)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tickets SET user_id='a', request_id='r', sold_at=now() WHERE ticket_no=1")
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute("UPDATE tickets SET user_id='b', request_id='r', sold_at=now() WHERE ticket_no=2")
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute("UPDATE tickets SET user_id='a', request_id='r2', sold_at=now() WHERE ticket_no=2")
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute("INSERT INTO tickets (ticket_no) VALUES (1)")


async def test_reset_bumps_epoch_and_clears_sales(pool):
    alloc = get("skiplocked")
    e1 = await reset(pool, 5)
    await buy(pool, alloc, "a", "ra")
    e2 = await reset(pool, 5)
    assert e2 == e1 + 1
    s = await status(pool, alloc)
    assert s["sold"] == 0 and s["total"] == 5 and s["epoch"] == e2


@pytest.mark.parametrize("name", SAFE)
async def test_twins_racing_for_the_last_ticket_are_never_told_sold_out(pool, name):
    """One copy of a request takes the last ticket while its twin waits on that
    row's lock; the twin must report the ticket (replayed), not 'sold out'."""
    alloc = get(name)
    for _ in range(20):  # the interleaving is timing-dependent; repeat to hit it
        await reset(pool, 1)
        results = await asyncio.gather(*(buy(pool, alloc, "last", "r-last") for _ in range(30)))
        assert not any(isinstance(r, SoldOut) for r in results), \
            f"{sum(isinstance(r, SoldOut) for r in results)}/30 twins told sold out"
        assert len({r.ticket_no for r in results}) == 1
