"""The live auditor must flag each mid-sale violation from snapshots alone."""

from buyer.auditor import AuditResult, check_snapshot
from buyer.verify import all_core_pass, verify

TOTAL = 3


def snap(pairs, sold=None, epoch=1):
    holders = [{"ticket_no": t, "user_id": u} for u, t in pairs]
    return {"epoch": epoch, "total": TOTAL, "sold": len(holders) if sold is None else sold, "holders": holders}


def run(*snapshots):
    result, prev = AuditResult(), None
    for i, s in enumerate(snapshots):
        check_snapshot(s, TOTAL, prev, result, t=i * 0.1)
        result.snapshots += 1
        prev = s
    return result


def test_growing_consistent_sale_is_clean():
    r = run(snap([]), snap([("a", 1)]), snap([("a", 1), ("b", 2)]), snap([("a", 1), ("b", 2), ("c", 3)]))
    assert not r.violations


def test_momentary_count_mismatch_is_caught():
    r = run(snap([("a", 1)]), snap([("a", 1), ("b", 2)], sold=1), snap([("a", 1), ("b", 2)]))
    assert r.violations == {"count_mismatch": 1}


def test_oversell_duplicate_and_double_holder_are_caught():
    r = run(snap([("a", 1), ("b", 1), ("a", 2), ("d", 4)]))
    assert {"oversell", "duplicate_ticket", "user_holds_two"} <= set(r.violations)


def test_vanished_sale_and_shrinking_count_are_caught():
    r = run(snap([("a", 1), ("b", 2)]), snap([("a", 1)]))
    assert r.violations["sale_vanished"] == 1 and r.violations["count_decreased"] == 1


def test_new_epoch_may_start_empty():
    r = run(snap([("a", 1)], epoch=1), snap([], epoch=2))
    assert not r.violations


def test_audit_violation_fails_the_run_even_if_final_status_is_clean():
    audit = run(snap([("a", 1)], sold=2), snap([("a", 1)]))
    final = snap([("a", 1)])
    from buyer.runner import Attempt
    attempts = [Attempt(kind="fresh", user_id="a", request_id="ra", sched=0, sent=0, done=0.01, status=200,
                        ticket_no=1, epoch=1)]
    checks = verify(final, attempts, TOTAL, audit=audit)
    a3 = next(c for c in checks if c.id == "A3")
    assert a3.passed is False
    assert not all_core_pass(checks)
