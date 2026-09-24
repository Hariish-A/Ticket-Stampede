# Seller CPU profile (py-spy)

1905 samples at 250 Hz over 10 s → the seller's Python thread was busy **76%** of the time (100% = one core saturated).

| layer | self (leaf) | inclusive |
|---|---|---|
| event loop (asyncio/uvloop) | 69% | 74% |
| framework & validation (FastAPI/Starlette/Pydantic) | 11% | 17% |
| DB driver (asyncpg) | 8% | 11% |
| HTTP server (uvicorn/httptools) | 5% | 72% |
| our code (app/) | 3% | 4% |
| other (stdlib, logging, ...) | 2% | 69% |
| JSON | 1% | 1% |

Top leaf frames:

| share | frame |
|---|---|
| 63.2% | `run (asyncio/runners.py:118)` |
| 1.8% | `_do_execute (asyncpg/connection.py:2027)` |
| 1.6% | `reschedule (asyncio/timeouts.py:71)` |
| 1.5% | `execute (asyncpg/connection.py:349)` |
| 1.4% | `data_received (uvicorn/protocols/http/httptools_impl.py:171)` |
| 0.9% | `buy (app/main.py:125)` |
| 0.7% | `body (starlette/requests.py:241)` |
| 0.7% | `send (uvicorn/protocols/http/httptools_impl.py:511)` |
| 0.7% | `__aexit__ (asyncio/timeouts.py:117)` |
| 0.6% | `app (starlette/routing.py:74)` |
| 0.5% | `solve_dependencies (fastapi/dependencies/utils.py:689)` |
| 0.5% | `ensure_future (asyncio/tasks.py:695)` |

O_DIRECT supported on this platform for open_datasync and open_sync.
(in wal_sync_method preference order, except fdatasync is Linux's default)
        open_datasync                       382.436 ops/sec    2615 usecs/op
        fdatasync                           379.032 ops/sec    2638 usecs/op
        fsync                               185.542 ops/sec    5390 usecs/op
(in wal_sync_method preference order, except fdatasync is Linux's default)
