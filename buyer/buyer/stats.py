from collections import Counter

from .runner import Attempt, WorkerResult


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
        "client": {
            "processes": len(workers),
            # Fraction of one core each worker used; ~100% means the client was the limit.
            "cpu_util_per_worker": [round(u, 3) for u in utils],
            "cpu_util_max": max(utils, default=0.0),
        },
        "by_status": dict(sorted(Counter(str(a.status) for a in attempts).items())),
        "by_kind": dict(sorted(Counter(a.kind for a in attempts).items())),
        "errors": dict(Counter(a.error for a in attempts if a.error)),
        "first_sold_out_at_s": round(min(sold_out) - t0, 3) if sold_out else None,
    }
