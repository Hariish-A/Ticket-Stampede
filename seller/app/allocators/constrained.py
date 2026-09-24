"""Shared flow for the safe allocators: the database constraints are the source
of truth, and the application only has to interpret what they allow.

    1. Look up an existing sale for this request_id or user_id.
    2. If there is none, try to claim a ticket (strategy-specific, one statement).
    3. If the claim trips a UNIQUE constraint, a concurrent request with the
       same request_id or user_id won the race; go back to 1 and report theirs.

There is deliberately no explicit transaction. The claim is a single atomic
UPDATE, and the constraints -- not a lock held across the lookup and the
claim -- are what stop a double sale. Skipping BEGIN/COMMIT saves two round
trips per request and keeps row locks held for exactly one statement.
"""

import asyncpg

from ..sale import BuyResult, Purchased, RequestIdConflict, SoldOut

LOOKUP = """
SELECT s.epoch, t.ticket_no, t.user_id, t.request_id
FROM sale s
LEFT JOIN tickets t ON t.request_id = $1 OR t.user_id = $2
WHERE s.id = 1
"""

# One statement, so `sold` and the holder list come from a single snapshot:
# the count cannot disagree with the list (I4) by construction.
STATUS = """
SELECT s.epoch, s.total, t.ticket_no, t.user_id
FROM sale s
LEFT JOIN tickets t ON t.user_id IS NOT NULL
WHERE s.id = 1
ORDER BY t.ticket_no
"""


class RetriesExhausted(Exception):
    """Kept losing UNIQUE races without ever seeing the winner; surfaces as 503."""


def resolve_existing(rows, user_id: str, request_id: str) -> BuyResult | None:
    by_rid = next((r for r in rows if r["request_id"] == request_id), None)
    if by_rid is not None:
        if by_rid["user_id"] != user_id:
            return RequestIdConflict()
        return Purchased(by_rid["ticket_no"], rows[0]["epoch"], replayed=True)
    by_user = next((r for r in rows if r["user_id"] == user_id), None)
    if by_user is not None:
        return Purchased(by_user["ticket_no"], rows[0]["epoch"], existing=True)
    return None


class ConstrainedAllocator:
    name = "abstract"
    max_attempts = 5

    async def claim(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> int | None:
        """Assign one unsold ticket to this buyer; None means definitively sold out."""
        raise NotImplementedError

    async def buy(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> BuyResult:
        for _ in range(self.max_attempts):
            rows = await conn.fetch(LOOKUP, request_id, user_id)
            known = resolve_existing(rows, user_id, request_id)
            if known is not None:
                return known
            try:
                ticket_no = await self.claim(conn, user_id, request_id)
            except asyncpg.UniqueViolationError:
                continue  # a concurrent twin committed first; the lookup will now find it
            epoch = rows[0]["epoch"]
            if ticket_no is not None:
                return Purchased(ticket_no, epoch)
            # Before saying "sold out", look again: a twin of this very request
            # (or this user's other request) may have taken the last ticket while
            # our claim waited on its row lock. Found by
            # test_twins_racing_for_the_last_ticket_are_never_told_sold_out.
            # Costs one extra query on the sold-out path (measured in M4/M5).
            again = await conn.fetch(LOOKUP, request_id, user_id)
            return resolve_existing(again, user_id, request_id) or SoldOut(epoch)
        raise RetriesExhausted(f"request_id={request_id!r} user_id={user_id!r}")

    async def status(self, conn: asyncpg.Connection) -> dict:
        rows = await conn.fetch(STATUS)
        holders = [{"ticket_no": r["ticket_no"], "user_id": r["user_id"]} for r in rows if r["ticket_no"] is not None]
        return {"epoch": rows[0]["epoch"], "total": rows[0]["total"], "sold": len(holders), "holders": holders}
