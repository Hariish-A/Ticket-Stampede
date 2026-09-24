"""Retries with the same request_id, and what the outcome accounting makes of them."""

import asyncio
import random
import socket

from aiohttp import web

from buyer.runner import Attempt, _attempt, _session, backoff, retryable
from buyer.schedule import FRESH, RETRY, Planned
from buyer.stats import buyer_outcomes, timeline


def att(rid, status, answer=None, ticket=None, replayed=False, t=0.0, n=0, user=None):
    return Attempt(kind=RETRY if n else FRESH, user_id=user or "u" + rid, request_id=rid, sched=t, sent=t,
                   done=t + 0.01, status=status, ticket_no=ticket, epoch=1, replayed=replayed,
                   answer=answer, attempt_no=n)


def test_outcomes_separate_recovered_from_bought_on_retry():
    attempts = [
        # r1: "unknown" had actually committed -> retry gets it back as a replay
        att("r1", 503, "unknown", t=0), att("r1", 200, "purchased", 7, replayed=True, t=1, n=1),
        # r2: nothing had been sent -> retry buys for the first time
        att("r2", 503, "not_attempted", t=0), att("r2", 200, "purchased", 8, t=1, n=1),
        # r3: never got a definite answer
        att("r3", 503, "unknown", t=0), att("r3", 0, t=1, n=1),
        # r4: definite on the first try
        att("r4", 409, "sold_out", t=0),
    ]
    o = buyer_outcomes(attempts)
    assert o["recovered_by_retry"] == 1
    assert o["bought_on_retry"] == 1
    assert o["had_unclear_answer"] == 3
    assert o["final"] == {"purchased": 2, "still_unknown": 1, "sold_out": 1}


def test_timeline_buckets_by_scheduled_time_and_counts_answers():
    attempts = [att("a", 200, "purchased", 1, t=0.2), att("b", 503, "unknown", t=0.7),
                att("c", 503, "not_attempted", t=1.5), att("d", 409, "sold_out", t=1.9, n=1)]
    rows = timeline(attempts, t0=0.0)
    assert [r["t_s"] for r in rows] == [0.0, 1.0]
    assert rows[0]["answers"] == {"purchased": 1, "unknown": 1}
    assert rows[1]["answers"] == {"not_attempted": 1, "sold_out": 1}
    assert rows[1]["retries"] == 1


def test_only_unclear_answers_are_retried_and_backoff_is_bounded():
    assert retryable(att("x", 503)) and retryable(att("x", 0))
    assert not any(retryable(att("x", s)) for s in (200, 409, 422))
    rng = random.Random(0)
    assert all(0.25 <= backoff(1, rng) <= 0.5 for _ in range(50))
    assert all(2.0 <= backoff(9, rng) <= 4.0 for _ in range(50))


def test_retry_loop_reuses_the_request_id_until_a_definite_answer():
    seen = []

    async def buy(request):
        body = await request.json()
        seen.append((body["user_id"], body["request_id"]))
        if len(seen) <= 2:
            return web.json_response({"status": "unknown"}, status=503)
        return web.json_response({"status": "purchased", "ticket_no": 5, "epoch": 1, "replayed": True})

    async def scenario():
        app = web.Application()
        app.router.add_post("/buy", buy)
        runner = web.AppRunner(app)
        await runner.setup()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        try:
            async with _session(f"http://127.0.0.1:{port}", timeout=5) as session:
                import buyer.runner as r
                orig, r.backoff = r.backoff, lambda n, rng: 0.01  # keep the test fast
                try:
                    return await _attempt(session, Planned(0, "alice", "rid-1", FRESH), None, 5, random.Random(0))
                finally:
                    r.backoff = orig
        finally:
            await runner.cleanup()

    attempts = asyncio.run(scenario())
    assert [a.status for a in attempts] == [503, 503, 200]
    assert seen == [("alice", "rid-1")] * 3  # every retry carried the same request_id
    assert [a.attempt_no for a in attempts] == [0, 1, 2]
    assert attempts[-1].replayed and attempts[-1].kind == RETRY


def test_retry_budget_caps_the_rate_but_never_drops():
    from buyer.runner import RetryBudget
    import time

    async def take(n, rate):
        b = RetryBudget(rate)
        start = time.perf_counter()
        for _ in range(n):
            await b.take()
        return time.perf_counter() - start

    # 50 retries at 100/s with a burst of 100: immediate. 250 at 100/s: ~1.5 s (150 over the burst).
    assert asyncio.run(take(50, 100)) < 0.1
    elapsed = asyncio.run(take(250, 100))
    assert 1.3 < elapsed < 2.0


def test_only_not_attempted_answers_mean_known_not_bought():
    attempts = [att("r5", 503, "not_attempted", t=0), att("r5", 503, "not_attempted", t=1, n=1),
                att("r6", 503, "not_attempted", t=0), att("r6", 503, "unknown", t=1, n=1)]
    assert buyer_outcomes(attempts)["final"] == {"turned_away_known": 1, "still_unknown": 1}


def test_inflight_at_fault_separates_committed_from_not():
    from buyer.stats import inflight_at
    attempts = [
        # sent before the fault at t=5, answered after
        Attempt(kind=FRESH, user_id="a", request_id="ra", sched=4.9, sent=4.9, done=5.5, status=503, answer="unknown"),
        Attempt(kind=RETRY, user_id="a", request_id="ra", sched=9, sent=9, done=9.1, status=200, ticket_no=3,
                replayed=True, attempt_no=1),
        Attempt(kind=FRESH, user_id="b", request_id="rb", sched=4.95, sent=4.95, done=5.2, status=0),
        Attempt(kind=RETRY, user_id="b", request_id="rb", sched=9, sent=9, done=9.1, status=200, ticket_no=4,
                attempt_no=1),
        Attempt(kind=FRESH, user_id="c", request_id="rc", sched=4.99, sent=4.99, done=5.01, status=200, ticket_no=5),
        # not in flight
        Attempt(kind=FRESH, user_id="d", request_id="rd", sched=1, sent=1, done=1.1, status=200, ticket_no=6),
    ]
    r = inflight_at(attempts, 5.0)
    assert r["in_flight"] == 3
    assert r["fates"] == {"unclear, then retry found it: HAD committed": 1,
                          "unclear, then bought on retry: had NOT committed": 1,
                          "answered: purchased (commit acknowledged before the kill)": 1}


def test_external_fault_file_is_placed_relative_to_t0(tmp_path):
    import json
    from buyer.faults import external_window
    p = tmp_path / "events.json"
    p.write_text(json.dumps({"kind": "kill", "detail": "SIGKILL postgres",
                             "events": {"fault": 1000.0, "restart": 1005.0, "recovered": 1007.5}}))
    w = external_window(str(p), t0_wall=992.0, wait_s=1)
    assert (w.kind, w.actual_start_s, w.actual_end_s) == ("kill", 8.0, 15.5)
    assert external_window(str(tmp_path / "missing.json"), 0, wait_s=0) is None


def test_any_5xx_is_unclear_and_retried():
    assert all(retryable(att("x", s)) for s in (500, 502, 503, 504))
    o = buyer_outcomes([att("r7", 500, t=0), att("r7", 200, "purchased", 9, replayed=True, t=1, n=1)])
    assert o["recovered_by_retry"] == 1 and o["final"] == {"purchased": 1}
