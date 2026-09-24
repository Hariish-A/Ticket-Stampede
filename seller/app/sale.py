"""Operations shared by every allocator: result types and /reset."""

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class Purchased:
    ticket_no: int
    epoch: int
    replayed: bool = False  # same request_id seen before; this is the original ticket
    existing: bool = False  # same user_id, new request_id; this is the ticket they already hold


@dataclass(frozen=True)
class SoldOut:
    epoch: int


@dataclass(frozen=True)
class RequestIdConflict:
    """The request_id is already bound to a different user_id."""


BuyResult = Purchased | SoldOut | RequestIdConflict


async def reset(conn: asyncpg.Connection, count: int) -> int:
    """Wipe every allocator's state and start sale `epoch + 1` with `count` tickets.

    TRUNCATE takes an ACCESS EXCLUSIVE lock, so it waits for in-flight buy
    transactions to finish and blocks new ones until the reset commits: a buy
    lands wholly in the old sale or wholly in the new one.
    """
    async with conn.transaction():
        await conn.execute("TRUNCATE naive_sales, tickets")
        await conn.execute("INSERT INTO tickets (ticket_no) SELECT generate_series(1, $1)", count)
        return await conn.fetchval(
            "UPDATE sale SET epoch = epoch + 1, total = $1, sold = 0 WHERE id = 1 RETURNING epoch",
            count,
        )
