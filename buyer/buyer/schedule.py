"""Builds the requests to fire and *when* to fire each one.

Phase 1 -- the stampede -- is open-loop: every request has a send time fixed
in advance, independent of how fast the seller answers. Latency is measured
from that scheduled time, so a stalled seller cannot quietly slow the client
down and hide its own stall (coordinated omission).

Phase 2 -- the probes -- is built *after* phase 1 from what actually
happened: replays and conflicts must target real winners. (An earlier version
guessed that the earliest requests would win; with a 1,000-request burst at
t=0 that guess was wrong and the probes silently tested nothing.)
"""

import random
from dataclasses import dataclass, replace
from typing import Iterable

FRESH = "fresh"
DUP_CONCURRENT = "dup_concurrent"  # same (user, request_id), same instant as the original
DUP_SEQUENTIAL = "dup_sequential"  # same (user, request_id), shortly after the original
REPLAY_AFTER = "replay_after_sellout"  # same (user, request_id), after the sale has ended
NEW_RID = "same_user_new_rid"  # a winner retrying with a new request_id (D7: gets their ticket)
RID_CONFLICT = "rid_conflict"  # a winner's request_id sent by a different user (must be 422)

RETRY = "retry"  # a client retry of an earlier 503/timeout, same (user, request_id); not scheduled

KINDS = (FRESH, DUP_CONCURRENT, DUP_SEQUENTIAL, REPLAY_AFTER, NEW_RID, RID_CONFLICT)


@dataclass(frozen=True, slots=True)
class Planned:
    t: float  # seconds after the phase starts
    user_id: str
    request_id: str
    kind: str


@dataclass(frozen=True)
class ScheduleSpec:
    requests: int  # distinct buyers, one fresh request each
    rate: float  # fresh requests per second after the opening burst
    burst: int  # this many fresh requests are all scheduled at t=0 (the on-sale moment)
    tickets: int
    dup_concurrent: int = 0
    dup_sequential: int = 0
    replay_after: int = 0
    new_rid: int = 0
    rid_conflict: int = 0
    seed: int = 1


def build(spec: ScheduleSpec) -> list[Planned]:
    """Phase 1: the stampede, with duplicates mixed in."""
    rng = random.Random(spec.seed)
    fresh = [
        Planned(
            t=0.0 if i < spec.burst else (i - spec.burst + 1) / spec.rate,
            user_id=f"u{i:06d}",
            request_id=f"r{i:06d}",
            kind=FRESH,
        )
        for i in range(spec.requests)
    ]
    extra = [replace(p, kind=DUP_CONCURRENT) for p in _pick(rng, fresh, spec.dup_concurrent)]
    extra += [replace(p, t=p.t + rng.uniform(0.05, 1.0), kind=DUP_SEQUENTIAL)
              for p in _pick(rng, fresh, spec.dup_sequential)]
    return sorted(fresh + extra, key=lambda p: p.t)


def build_probes(spec: ScheduleSpec, outcomes: Iterable) -> list[Planned]:
    """Phase 2, fired all at once after the stampede, aimed using phase 1's outcomes.

    `outcomes` are phase-1 attempts (anything with kind/user_id/request_id/confirmed).
    Replays go mostly to winners (who must get their ticket back, not "sold out")
    and partly to losers (who must still be sold out).
    """
    rng = random.Random(spec.seed + 1)
    winners, losers, seen = [], [], set()
    for a in outcomes:
        if a.kind != FRESH or a.request_id in seen:
            continue
        seen.add(a.request_id)
        (winners if a.confirmed else losers).append(Planned(0.0, a.user_id, a.request_id, FRESH))
    winners.sort(key=lambda p: p.request_id)
    losers.sort(key=lambda p: p.request_id)

    n_win = min(len(winners), -(-spec.replay_after * 4 // 5))  # ~80% of replays to winners
    probes = [replace(p, kind=REPLAY_AFTER) for p in _pick(rng, winners, n_win)]
    probes += [replace(p, kind=REPLAY_AFTER) for p in _pick(rng, losers, spec.replay_after - n_win)]
    probes += [Planned(0.0, p.user_id, p.request_id + "-b", NEW_RID) for p in _pick(rng, winners, spec.new_rid)]
    probes += [Planned(0.0, "x" + p.user_id, p.request_id, RID_CONFLICT) for p in _pick(rng, winners, spec.rid_conflict)]
    return probes


def _pick(rng: random.Random, pool: list[Planned], k: int) -> list[Planned]:
    return rng.sample(pool, min(max(k, 0), len(pool)))
