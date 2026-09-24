"""Let the database find the races: SERIALIZABLE isolation plus retry.

The textbook answer to "make read-then-write safe". Read the lowest unsold
ticket, write it, and let Postgres abort whichever of two overlapping
transactions would break serialisability (SQLSTATE 40001); retry the loser.
Under a stampede nearly every buyer reads the *same* lowest ticket, so most
transactions abort and retry: correct, but paid for in retries and tail
latency. The retry count is exposed on /metrics and compared in C2.
"""

import asyncpg

from .constrained import ConstrainedAllocator, RetriesExhausted

MAX_TX_RETRIES = 50

READ_LOWEST = "SELECT ticket_no FROM tickets WHERE user_id IS NULL ORDER BY ticket_no LIMIT 1"
WRITE = "UPDATE tickets SET user_id = $1, request_id = $2, sold_at = clock_timestamp() WHERE ticket_no = $3"


class SerializableAllocator(ConstrainedAllocator):
    name = "serializable"

    async def claim(self, conn: asyncpg.Connection, user_id: str, request_id: str) -> int | None:
        for _ in range(MAX_TX_RETRIES):
            try:
                async with conn.transaction(isolation="serializable"):
                    ticket_no = await conn.fetchval(READ_LOWEST)
                    if ticket_no is not None:
                        await conn.execute(WRITE, user_id, request_id, ticket_no)
                    return ticket_no
            except (asyncpg.SerializationError, asyncpg.DeadlockDetectedError):
                self.counters["serialization_retries"] += 1
        self.counters["serialization_gave_up"] += 1
        raise RetriesExhausted(f"serializable claim retried {MAX_TX_RETRIES} times")
