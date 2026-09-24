"""All tunables come from the environment so the same image runs locally, in
compose with 1 or 3 instances, or against a managed Postgres."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    allocator: str
    pool_min: int
    pool_max: int
    pool_acquire_timeout: float  # seconds to wait for a free connection before answering 503
    command_timeout: float  # seconds any single query may take before answering 503
    statement_cache_size: int  # set to 0 behind a transaction-mode pooler (PgBouncer, Supavisor)
    max_inflight: int  # /buy requests allowed inside the seller at once; beyond it, 503 at once (0 = no limit)


def load() -> Settings:
    env = os.environ.get
    return Settings(
        database_url=env("DATABASE_URL", "postgresql://tickets:tickets@localhost:5432/tickets"),
        allocator=env("ALLOCATOR", "naive"),
        pool_min=int(env("POOL_MIN", "5")),
        pool_max=int(env("POOL_MAX", "20")),
        pool_acquire_timeout=float(env("POOL_ACQUIRE_TIMEOUT", "1.0")),
        command_timeout=float(env("COMMAND_TIMEOUT", "2.0")),
        statement_cache_size=int(env("STATEMENT_CACHE_SIZE", "100")),
        max_inflight=int(env("MAX_INFLIGHT", "0")),
    )
