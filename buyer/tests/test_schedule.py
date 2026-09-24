from collections import Counter
from types import SimpleNamespace

from buyer.schedule import (DUP_CONCURRENT, DUP_SEQUENTIAL, FRESH, NEW_RID, REPLAY_AFTER, RID_CONFLICT,
                            ScheduleSpec, build, build_probes)

SPEC = ScheduleSpec(requests=1000, rate=100, burst=200, tickets=10, dup_concurrent=30, dup_sequential=20,
                    replay_after=10, new_rid=4, rid_conflict=3, seed=42)


def test_phase1_counts_per_kind():
    kinds = Counter(p.kind for p in build(SPEC))
    assert kinds == {FRESH: 1000, DUP_CONCURRENT: 30, DUP_SEQUENTIAL: 20}


def test_burst_is_at_t0_and_rest_is_paced():
    fresh = [p for p in build(SPEC) if p.kind == FRESH]
    assert sum(1 for p in fresh if p.t == 0.0) == 200
    assert max(p.t for p in fresh) == (1000 - 200) / 100


def test_deterministic_for_a_seed():
    assert build(SPEC) == build(SPEC)


def test_sorted_by_time():
    ts = [p.t for p in build(SPEC)]
    assert ts == sorted(ts)


def test_duplicates_reuse_identity():
    plan = build(SPEC)
    originals = {p.request_id: p for p in plan if p.kind == FRESH}
    for p in plan:
        if p.kind in (DUP_CONCURRENT, DUP_SEQUENTIAL):
            assert originals[p.request_id].user_id == p.user_id
        if p.kind == DUP_CONCURRENT:
            assert originals[p.request_id].t == p.t


def outcome(i, won):
    return SimpleNamespace(kind=FRESH, user_id=f"u{i}", request_id=f"r{i}", confirmed=won)


def test_probes_target_actual_winners_not_early_requests():
    # Winners are deliberately the *last* requests: the old "earliest = winners" guess would miss them all.
    outcomes = [outcome(i, won=i >= 990) for i in range(1000)]
    winners = {f"r{i}" for i in range(990, 1000)}
    probes = build_probes(SPEC, outcomes)
    kinds = Counter(p.kind for p in probes)
    assert kinds == {REPLAY_AFTER: 10, NEW_RID: 4, RID_CONFLICT: 3}
    replays = [p for p in probes if p.kind == REPLAY_AFTER]
    assert sum(p.request_id in winners for p in replays) == 8  # ~80% to winners
    assert all(p.request_id in winners for p in probes if p.kind == RID_CONFLICT)
    assert all(p.user_id.startswith("x") for p in probes if p.kind == RID_CONFLICT)
    assert all(p.request_id.removesuffix("-b") in winners and p.request_id.endswith("-b")
               for p in probes if p.kind == NEW_RID)


def test_probes_survive_having_no_winners():
    probes = build_probes(SPEC, [outcome(i, won=False) for i in range(50)])
    assert Counter(p.kind for p in probes) == {REPLAY_AFTER: 10 - 0}  # all replays go to losers
