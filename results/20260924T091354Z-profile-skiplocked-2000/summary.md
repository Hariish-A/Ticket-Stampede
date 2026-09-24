# Seller CPU profile (py-spy)

1866 samples at 250 Hz over 10 s → the seller's Python thread was busy **75%** of the time (100% = one core saturated).

| layer | self (leaf) | inclusive |
|---|---|---|
| event loop (asyncio/uvloop) | 35% | 71% |
| framework & validation (FastAPI/Starlette/Pydantic) | 26% | 49% |
| other (stdlib, logging, ...) | 13% | 66% |
| DB driver (asyncpg) | 13% | 18% |
| HTTP server (uvicorn/httptools) | 11% | 69% |
| our code (app/) | 2% | 14% |
| JSON | 0% | 0% |

Top leaf frames:

| share | frame |
|---|---|
| 26.6% | `run (asyncio/runners.py:118)` |
| 4.3% | `parse_qsl (urllib/parse.py:757)` |
| 3.6% | `wrap_app_handling_exceptions (starlette/_exception_handler.py:23)` |
| 3.3% | `get (asyncio/queues.py:163)` |
| 3.1% | `__init__ (contextlib.py:482)` |
| 3.1% | `run_asgi (uvicorn/protocols/http/httptools_impl.py:410)` |
| 2.7% | `__delitem__ (starlette/datastructures.py:597)` |
| 2.4% | `_do_execute (asyncpg/connection.py:2029)` |
| 2.3% | `wrapped_app (starlette/_exception_handler.py:31)` |
| 2.0% | `__aenter__ (asyncpg/pool.py:1021)` |
| 1.9% | `_check_init (asyncpg/pool.py:977)` |
| 1.8% | `_do_execute (asyncpg/connection.py:2027)` |

O_DIRECT supported on this platform for open_datasync and open_sync.
(in wal_sync_method preference order, except fdatasync is Linux's default)
        open_datasync                       367.524 ops/sec    2721 usecs/op
        fdatasync                           372.228 ops/sec    2687 usecs/op
        fsync                               179.100 ops/sec    5583 usecs/op
(in wal_sync_method preference order, except fdatasync is Linux's default)
