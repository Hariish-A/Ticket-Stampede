"""Builds the list of requests to fire and *when* to fire each one.

The buyer is open-loop: every request has a scheduled send time fixed in
advance, independent of how fast the seller answers. Latency is measured from
that scheduled time, so a stalled seller cannot quietly slow the client down
and hide its own stall (coordinated omission).
"""

import random
from dataclasses import dataclass, replace

FRESH = "fresh"
DUP_CONCURRENT = "dup_concurrent"  # same (user, request_id), same instant as the original
DUP_SEQUENTIAL = "dup_sequential"  # same (user, request_id), shortly after the original
REPLAY_AFTER = "replay_after_sellout"  # same (user, request_id), after the sale has ended
NEW_RID = "same_user_new_rid"  # same user, different request_id (one ticket per user)
RID_CONFLICT = "rid_conflict"  # same request_id, different user (must be rejected)

KINDS = (FRESH, DUP_CONCURRENT, DUP_SEQUENTIAL, REPLAY_AFTER, NEW_RID, RID_CONFLICT)


@dataclass(frozen=True, slots=True)
class Planned:
    t: float  # seconds after the run starts
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
    if not fresh:
        return []
    end = fresh[-1].t + 0.5

    # Replays that should hit *winners* are drawn from the earliest requests,
    # which are the ones most likely to have bought a ticket.
    early = fresh[: min(len(fresh), max(spec.tickets * 3, 1))]

    def pick(pool: list[Planned], k: int) -> list[Planned]:
        return rng.sample(pool, min(k, len(pool)))

    extra = [replace(p, kind=DUP_CONCURRENT) for p in pick(fresh, spec.dup_concurrent)]
    extra += [replace(p, t=p.t + rng.uniform(0.05, 1.0), kind=DUP_SEQUENTIAL) for p in pick(fresh, spec.dup_sequential)]
    extra += [replace(p, t=end, kind=REPLAY_AFTER) for p in pick(early, spec.replay_after)]
    extra += [Planned(end, p.user_id, p.request_id + "-b", NEW_RID) for p in pick(early, spec.new_rid)]
    extra += [Planned(end, "x" + p.user_id, p.request_id, RID_CONFLICT) for p in pick(early, spec.rid_conflict)]

    return sorted(fresh + extra, key=lambda p: p.t)
