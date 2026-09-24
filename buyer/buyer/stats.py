from collections import Counter

from .runner import Attempt, WorkerResult, retryable


def percentile(sorted_values: list[float], q: float) -> float | None:
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_values:
        return None
    rank = max(1, round(q / 100 * len(sorted_values) + 0.5))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def distribution(values_ms: list[float]) -> dict:
    v = sorted(values_ms)
    return {
        "count": len(v),
        "p50": percentile(v, 50),
        "p90": percentile(v, 90),
        "p99": percentile(v, 99),
        "max": v[-1] if v else None,
    }


def answer_class(a: Attempt) -> str:
    if a.status == 0:
        return "no_response"
    if a.status == 503:
        return a.answer if a.answer in ("unknown", "not_attempted") else "503"
    return {200: "purchased", 409: "sold_out", 422: "conflict"}.get(a.status, str(a.status))


def timeline(attempts: list[Attempt], t0: float, bucket_s: float = 1.0) -> list[dict]:
    """Per-second view, bucketed by when each request was *meant* to go out (its
    scheduled time; for closed-loop, when it actually went out). Retries included:
    they are load too. A stall shows up here as latency climbing in the buckets
    it covers -- or, for a closed-loop client, as buckets that simply go quiet."""
    buckets: dict[int, list[Attempt]] = {}
    for a in attempts:
        buckets.setdefault(int((a.sched - t0) // bucket_s), []).append(a)
    rows = []
    for b in sorted(buckets):
        group = buckets[b]
        lat = sorted((a.done - a.sched) * 1000 for a in group if a.status)
        rows.append({"t_s": b * bucket_s, "sent": len(group),
                     "answers": dict(Counter(answer_class(a) for a in group)),
                     "retries": sum(1 for a in group if a.attempt_no),
                     "p50_ms": percentile(lat, 50), "p99_ms": percentile(lat, 99)})
    return rows


def buyer_outcomes(attempts: list[Attempt]) -> dict:
    """What each buyer (user_id, request_id) ended up with after all retries --
    the question a real person cares about -- and what the retries revealed."""
    by_key: dict[tuple, list[Attempt]] = {}
    for a in sorted(attempts, key=lambda a: (a.sent, a.attempt_no)):
        by_key.setdefault((a.user_id, a.request_id), []).append(a)
    final, recovered, bought_on_retry, retried = Counter(), 0, 0, 0
    for tries in by_key.values():
        definite = [a for a in tries if not retryable(a)]
        if definite:
            final[answer_class(definite[-1])] += 1
        elif all(a.answer == "not_attempted" for a in tries):
            # Every answer said "nothing was sent to the database": this buyer
            # definitely did NOT buy. Known, unlike "unknown".
            final["turned_away_known"] += 1
        else:
            final["still_unknown"] += 1
        first_unclear = next((i for i, a in enumerate(tries) if retryable(a)), None)
        if first_unclear is None:
            continue
        retried += 1
        later_ok = next((a for a in tries[first_unclear + 1:] if a.confirmed), None)
        if later_ok is not None and later_ok.replayed:
            recovered += 1  # an earlier "unknown" had in fact committed; the retry found it
        elif later_ok is not None:
            bought_on_retry += 1  # nothing had committed; the retry bought afresh
    return {"buyers": len(by_key), "final": dict(final), "had_unclear_answer": retried,
            "recovered_by_retry": recovered, "bought_on_retry": bought_on_retry}


def inflight_at(attempts: list[Attempt], t_fault: float) -> dict:
    """Requests that were on the wire at the instant of a fault (sent before, answered
    after) and what became of each buyer. This is the direct evidence that a kill
    landed *during* purchases -- some of which committed and some of which did not."""
    by_key: dict[tuple, list[Attempt]] = {}
    for a in sorted(attempts, key=lambda a: (a.sent, a.attempt_no)):
        by_key.setdefault((a.user_id, a.request_id), []).append(a)
    caught = [a for a in attempts if a.sent <= t_fault < a.done]
    fates = Counter()
    for a in caught:
        later = [b for b in by_key[(a.user_id, a.request_id)] if b.sent > a.sent]
        if a.confirmed:
            fates["answered: purchased (commit acknowledged before the kill)"] += 1
        elif not retryable(a):
            fates[f"answered: {answer_class(a)}"] += 1
        elif any(b.confirmed and b.replayed for b in later):
            fates["unclear, then retry found it: HAD committed"] += 1
        elif any(b.confirmed for b in later):
            fates["unclear, then bought on retry: had NOT committed"] += 1
        elif any(b.status == 409 for b in later):
            fates["unclear, then sold out on retry"] += 1
        else:
            fates["unclear, never resolved"] += 1
    return {"in_flight": len(caught), "fates": dict(fates)}


def summarize(attempts: list[Attempt], t0: float, workers: list[WorkerResult] = ()) -> dict:
    responded = [a for a in attempts if a.status]
    first_sent = min((a.sent for a in attempts), default=t0)
    last_done = max((a.done for a in attempts), default=t0)
    window = max(last_done - first_sent, 1e-9)
    sold_out = [a.done for a in attempts if a.status == 409]
    utils = [w.cpu_util for w in workers]

    return {
        "requests_sent": len(attempts),
        "responses": len(responded),
        "no_response": len(attempts) - len(responded),
        "window_s": round(window, 3),
        "throughput_rps": round(len(responded) / window, 1),
        # From the *scheduled* send time: what a buyer actually waited, including
        # any time the client itself fell behind (open-loop / no coordinated omission).
        "latency_ms": distribution([(a.done - a.sched) * 1000 for a in responded]),
        # From the actual send: the seller's response time alone.
        "service_ms": distribution([(a.done - a.sent) * 1000 for a in responded]),
        # How late the client was in sending. If this grows, the client -- not
        # the seller -- is the bottleneck and the run's numbers are suspect.
        "send_lag_ms": distribution([(a.sent - a.sched) * 1000 for a in attempts]),
        # Where the seller's time went (Server-Timing). `outside_handler` = the buyer's
        # service time minus the handler's own time: HTTP parsing, waiting for the
        # event loop, network. It grows when the seller process is CPU-bound.
        "server_ms": {
            "acq": distribution([a.srv_acq for a in responded if a.srv_acq is not None]),
            "alloc": distribution([a.srv_alloc for a in responded if a.srv_alloc is not None]),
            "handler": distribution([a.srv_handler for a in responded if a.srv_handler is not None]),
            "outside_handler": distribution([(a.done - a.sent) * 1000 - a.srv_handler
                                             for a in responded if a.srv_handler is not None]),
        },
        "client": {
            "processes": len(workers),
            # Fraction of one core each worker used; ~100% means the client was the limit.
            "cpu_util_per_worker": [round(u, 3) for u in utils],
            "cpu_util_max": max(utils, default=0.0),
        },
        "by_status": dict(sorted(Counter(str(a.status) for a in attempts).items())),
        "by_answer": dict(sorted(Counter(answer_class(a) for a in attempts).items())),
        "by_kind": dict(sorted(Counter(a.kind for a in attempts).items())),
        "errors": dict(Counter(a.error for a in attempts if a.error)),
        "first_sold_out_at_s": round(min(sold_out) - t0, 3) if sold_out else None,
        "outcomes": buyer_outcomes(attempts),
        "timeline": timeline(attempts, t0),
    }
