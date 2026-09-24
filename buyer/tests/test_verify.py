"""Testing the tester: a PASS from the verifier is only worth something if it
demonstrably FAILs each kind of violation. Every test here plants one defect."""

from buyer.runner import Attempt
from buyer.schedule import DUP_CONCURRENT, FRESH, NEW_RID, REPLAY_AFTER, RID_CONFLICT
from buyer.verify import all_core_pass, verify

TOTAL = 3


def ok(user, rid, ticket, kind=FRESH, **kw):
    return Attempt(kind=kind, user_id=user, request_id=rid, sched=0, sent=0, done=0.01,
                   status=200, ticket_no=ticket, epoch=1, **kw)


def sold_out(user, rid, kind=FRESH):
    return Attempt(kind=kind, user_id=user, request_id=rid, sched=0, sent=0, done=0.01, status=409, epoch=1)


def status_of(pairs, sold=None, epoch=1):
    holders = [{"ticket_no": t, "user_id": u} for u, t in pairs]
    return {"epoch": epoch, "total": TOTAL, "sold": len(holders) if sold is None else sold, "holders": holders}


def clean():
    attempts = [ok("a", "ra", 1), ok("b", "rb", 2), ok("c", "rc", 3), sold_out("d", "rd"),
                ok("a", "ra", 1, kind=DUP_CONCURRENT, replayed=True),
                ok("b", "rb", 2, kind=REPLAY_AFTER, replayed=True),
                ok("c", "rc-b", 3, kind=NEW_RID, existing=True),
                Attempt(kind=RID_CONFLICT, user_id="xa", request_id="ra", sched=0, sent=0, done=0.01, status=422)]
    return status_of([("a", 1), ("b", 2), ("c", 3)]), attempts


def verdicts(status, attempts):
    return {c.id: c.passed for c in verify(status, attempts, TOTAL)}


def test_clean_run_passes_everything():
    status, attempts = clean()
    v = verdicts(status, attempts)
    assert all(v[k] for k in ("I1", "I2", "I3", "I4", "U1", "U2", "U3", "U4"))
    assert all_core_pass(verify(status, attempts, TOTAL))


def test_oversell_in_status_fails_i1():
    status = status_of([("a", 1), ("b", 2), ("c", 3), ("d", 4)])
    attempts = [ok("a", "ra", 1), ok("b", "rb", 2), ok("c", "rc", 3), ok("d", "rd", 4)]
    assert verdicts(status, attempts)["I1"] is False


def test_oversell_hidden_from_status_is_still_caught():
    # /status looks perfect, but four buyers were each told they hold a ticket.
    status = status_of([("a", 1), ("b", 2), ("c", 3)])
    attempts = [ok("a", "ra", 1), ok("b", "rb", 2), ok("c", "rc", 3), ok("d", "rd", 3)]
    v = verdicts(status, attempts)
    assert v["I1"] is False
    assert v["I2"] is False  # ticket 3 confirmed to both c and d
    assert v["I4"] is False  # d's ticket is a phantom


def test_duplicate_ticket_number_in_status_fails_i2():
    status = status_of([("a", 1), ("b", 1)])
    attempts = [ok("a", "ra", 1), ok("b", "rb", 1)]
    assert verdicts(status, attempts)["I2"] is False


def test_same_request_id_two_tickets_fails_i3():
    status = status_of([("a", 1), ("a", 2)])
    attempts = [ok("a", "ra", 1), ok("a", "ra", 2, kind=DUP_CONCURRENT)]
    assert verdicts(status, attempts)["I3"] is False


def test_count_disagreeing_with_list_fails_i4():
    status = status_of([("a", 1), ("b", 2)], sold=1)
    attempts = [ok("a", "ra", 1), ok("b", "rb", 2)]
    assert verdicts(status, attempts)["I4"] is False


def test_phantom_confirmed_sale_missing_from_status_fails_i4():
    status = status_of([("a", 1)])
    attempts = [ok("a", "ra", 1), ok("b", "rb", 2)]
    assert verdicts(status, attempts)["I4"] is False


def test_orphan_is_reported_but_not_a_failure():
    status = status_of([("a", 1), ("b", 2)])
    attempts = [ok("a", "ra", 1),
                Attempt(kind=FRESH, user_id="b", request_id="rb", sched=0, sent=0, done=5, status=0, error="TimeoutError")]
    checks = {c.id: c for c in verify(status, attempts, TOTAL)}
    assert checks["A2"].passed is None
    assert "1 tickets" in checks["A2"].detail
    assert all_core_pass(list(checks.values()))


def test_user_with_two_tickets_fails_u1():
    status = status_of([("a", 1), ("a", 2)])
    attempts = [ok("a", "ra", 1), ok("a", "ra-b", 2, kind=NEW_RID)]
    assert verdicts(status, attempts)["U1"] is False


def test_request_id_conflict_not_rejected_fails_u2():
    status = status_of([("a", 1), ("xa", 2)])
    attempts = [ok("a", "ra", 1), ok("xa", "ra", 2, kind=RID_CONFLICT)]
    assert verdicts(status, attempts)["U2"] is False


def test_sold_out_while_tickets_remain_fails_u3():
    status = status_of([("a", 1)])
    attempts = [ok("a", "ra", 1), sold_out("b", "rb")]
    assert verdicts(status, attempts)["U3"] is False


def test_response_from_another_epoch_fails_u4():
    status, attempts = clean()
    attempts.append(Attempt(kind=FRESH, user_id="z", request_id="rz", sched=0, sent=0, done=0.01, status=409, epoch=7))
    assert verdicts(status, attempts)["U4"] is False
