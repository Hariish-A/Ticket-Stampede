from collections import Counter

from buyer.schedule import (DUP_CONCURRENT, DUP_SEQUENTIAL, FRESH, NEW_RID, REPLAY_AFTER, RID_CONFLICT,
                            ScheduleSpec, build)

SPEC = ScheduleSpec(requests=1000, rate=100, burst=200, tickets=10, dup_concurrent=30, dup_sequential=20,
                    replay_after=5, new_rid=4, rid_conflict=3, seed=42)


def test_counts_per_kind():
    kinds = Counter(p.kind for p in build(SPEC))
    assert kinds == {FRESH: 1000, DUP_CONCURRENT: 30, DUP_SEQUENTIAL: 20, REPLAY_AFTER: 5, NEW_RID: 4, RID_CONFLICT: 3}


def test_burst_is_at_t0_and_rest_is_paced():
    fresh = [p for p in build(SPEC) if p.kind == FRESH]
    assert sum(1 for p in fresh if p.t == 0.0) == 200
    assert max(p.t for p in fresh) == (1000 - 200) / 100


def test_deterministic_for_a_seed():
    assert build(SPEC) == build(SPEC)


def test_sorted_by_time():
    ts = [p.t for p in build(SPEC)]
    assert ts == sorted(ts)


def test_duplicates_reuse_identity_and_conflicts_do_not():
    plan = build(SPEC)
    originals = {p.request_id: p for p in plan if p.kind == FRESH}
    for p in plan:
        if p.kind in (DUP_CONCURRENT, DUP_SEQUENTIAL, REPLAY_AFTER):
            assert originals[p.request_id].user_id == p.user_id
        if p.kind == DUP_CONCURRENT:
            assert originals[p.request_id].t == p.t
        if p.kind == RID_CONFLICT:
            assert originals[p.request_id].user_id != p.user_id
        if p.kind == NEW_RID:
            assert p.request_id not in originals
