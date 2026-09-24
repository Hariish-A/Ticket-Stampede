"""Claim the lowest unsold ticket, skipping rows other buyers are mid-claim on.

Concurrent buyers each lock a *different* row instead of queueing on one, so
the sale proceeds in parallel.

SKIP LOCKED has a trap: "no row found" may only mean every remaining unsold
row is locked by an in-flight claim that could still fail (a UNIQUE violation
rolls it back). Answering "sold out" then would turn a buyer away while a
ticket goes unsold. So an empty fast path falls back to the same claim
*without* SKIP LOCKED, which waits for those in-flight claims to resolve and
takes a ticket if one comes back. Only if that also finds nothing is the sale
definitively sold out. The fallback only ever runs in the last moments of the
sale and after it.
"""

import asyncpg

from .constrained import ConstrainedAllocator

_CLAIM = """
UPDATE tickets
SET user_id = $1, request_id = $2, sold_at = clock_timestamp()
WHERE ticket_no = (
    SELECT ticket_no FROM tickets
    WHERE user_id IS NULL
    ORDER BY ticket_no
    LIMIT 1
    FOR UPDATE{skip}
)
AND user_id IS NULL
RETURNING ticket_no
"""
CLAIM_SKIP_LOCKED = _CLAIM.format(skip=" SKIP LOCKED")
CLAIM_WAIT = _CLAIM.format(skip="")


class SkipLockedAllocator(ConstrainedAllocator):
    name = "skiplocked"

    async def claim(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> int | None:
        ticket_no = await conn.fetchval(CLAIM_SKIP_LOCKED, user_id, request_id)
        if ticket_no is None:
            self.counters["blocking_fallbacks"] += 1
            ticket_no = await conn.fetchval(CLAIM_WAIT, user_id, request_id)
        return ticket_no
