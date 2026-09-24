"""The naive seller: the version most people write first, kept to be caught.

It reads the counter, decides, then writes -- as three separate statements
with no transaction, no locking and no constraints. Every `await` between the
read and the writes is a point where other requests read the same counter.

What breaks, and which invariant catches it:
  * N requests read sold=99 and all sell ticket 100      -> I1 oversell, I2 duplicate number
  * the write-back `sold = ticket_no` loses increments    -> I4 count != tickets issued
  * no request_id lookup, so a retried request buys again -> I3 idempotency
"""

from collections import Counter

import asyncpg

from ..sale import BuyResult, Purchased, SoldOut


class NaiveAllocator:
    name = "naive"

    def __init__(self) -> None:
        self.counters: Counter = Counter()

    async def buy(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> BuyResult:
        sale = await conn.fetchrow("SELECT epoch, total, sold FROM sale WHERE id = 1")
        if sale["sold"] >= sale["total"]:
            return SoldOut(sale["epoch"])
        ticket_no = sale["sold"] + 1
        await conn.execute(
            "INSERT INTO naive_sales (ticket_no, user_id, request_id) VALUES ($1, $2, $3)",
            ticket_no,
            user_id,
            request_id,
        )
        await conn.execute("UPDATE sale SET sold = $1 WHERE id = 1", ticket_no)
        return Purchased(ticket_no, sale["epoch"])

    async def status(self, conn: asyncpg.Connection) -> dict:
        # Reports its own counter next to the rows, as a naive service would.
        sale = await conn.fetchrow("SELECT epoch, total, sold FROM sale WHERE id = 1")
        rows = await conn.fetch("SELECT ticket_no, user_id FROM naive_sales ORDER BY ticket_no, sold_at")
        return {
            "epoch": sale["epoch"],
            "total": sale["total"],
            "sold": sale["sold"],
            "holders": [{"ticket_no": r["ticket_no"], "user_id": r["user_id"]} for r in rows],
        }
