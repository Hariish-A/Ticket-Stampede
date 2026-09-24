"""One shared counter row: the textbook "decrement the stock" design.

    UPDATE sale SET sold = sold + 1 WHERE sold < total RETURNING sold

and the new value *is* the ticket number. It is correct -- the row lock
serialises every increment -- but that is also its cost: every buyer queues
on the same row, and each holds the lock until its commit is flushed to disk.
Throughput is bounded by commit latency (the "hot row" problem); M1's naive
seller showed the same ceiling. Measured against skiplocked in C2.

Counter increment and ticket fill are one statement, so they commit or roll
back together (a UNIQUE violation also undoes the increment). Because the
counter serialises claims, there is no SKIP LOCKED "false sold out" trap here:
a claim that rolls back is waited for, and its number is re-evaluated.
"""

import asyncpg

from .constrained import ConstrainedAllocator

CLAIM = """
WITH next AS (
    UPDATE sale SET sold = sold + 1
    WHERE id = 1 AND sold < total
    RETURNING sold
)
UPDATE tickets
SET user_id = $1, request_id = $2, sold_at = clock_timestamp()
WHERE ticket_no = (SELECT sold FROM next) AND user_id IS NULL
RETURNING ticket_no
"""


class CounterAllocator(ConstrainedAllocator):
    name = "counter"

    async def claim(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> int | None:
        return await conn.fetchval(CLAIM, user_id, request_id)
