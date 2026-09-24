import asyncio
import logging
from pathlib import Path

import asyncpg

from .config import Settings

log = logging.getLogger(__name__)

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
SCHEMA_LOCK_KEY = 7_417_001  # arbitrary; serialises schema setup across instances


async def create_pool(settings: Settings, attempts: int = 30) -> asyncpg.Pool:
    """Postgres may still be starting when the seller boots; retry rather than crash."""
    for attempt in range(1, attempts + 1):
        try:
            return await asyncpg.create_pool(
                settings.database_url,
                min_size=settings.pool_min,
                max_size=settings.pool_max,
                command_timeout=settings.command_timeout,
                statement_cache_size=settings.statement_cache_size,
            )
        except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as exc:
            if attempt == attempts:
                raise
            log.warning("postgres not ready (%s), retry %d/%d", exc, attempt, attempts)
            await asyncio.sleep(1)
    raise AssertionError("unreachable")


async def apply_schema(pool: asyncpg.Pool) -> None:
    # Several instances start at once; concurrent CREATE TABLE IF NOT EXISTS can
    # still collide in the catalog, so take a transaction-scoped advisory lock.
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", SCHEMA_LOCK_KEY)
        await conn.execute(SCHEMA.read_text())
