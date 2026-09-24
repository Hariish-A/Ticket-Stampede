"""Checks the four invariants -- against /status AND against what the buyer was told.

/status is the seller grading its own homework. So every check also looks at
the client's ledger of responses: a sale the seller confirmed to a buyer but
does not report (a phantom) is a lost sale that /status alone can never reveal.

A "confirmed pair" is (user_id, ticket_no) from a 200 response: one physical
ticket in one person's hand. Replays and "you already hold one" answers repeat
the same pair, so they do not inflate the count.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from .runner import Attempt
from .schedule import DUP_CONCURRENT, DUP_SEQUENTIAL, FRESH, REPLAY_AFTER, RETRY, RID_CONFLICT

EXAMPLES = 5
REPEATS = (DUP_CONCURRENT, DUP_SEQUENTIAL, REPLAY_AFTER, RETRY)


@dataclass
class Check:
    id: str
    name: str
    passed: bool | None  # None = informational, not pass/fail
    detail: str
    examples: list = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "INFO" if self.passed is None else ("PASS" if self.passed else "FAIL")


def verify(status: dict, attempts: Iterable[Attempt], total: int, audit=None) -> list[Check]:
    attempts = list(attempts)
    holders = status.get("holders", [])
    sold = status.get("sold")
    confirmed = [a for a in attempts if a.confirmed]
    pairs = {(a.user_id, a.ticket_no) for a in confirmed}
    status_pairs = {(h["user_id"], h["ticket_no"]) for h in holders}

    checks: list[Check] = []

    # I1 -- never sell more tickets than exist.
    out_of_range = sorted({t for _, t in pairs | status_pairs if not 1 <= t <= total})
    problems = []
    if sold is None or sold > total:
        problems.append(f"/status sold={sold} > total={total}")
    if len(holders) > total:
        problems.append(f"/status lists {len(holders)} holders > total={total}")
    if len(pairs) > total:
        problems.append(f"buyers were confirmed {len(pairs)} distinct tickets > total={total}")
    if out_of_range:
        problems.append(f"ticket numbers outside 1..{total}: {out_of_range[:EXAMPLES]}")
    checks.append(Check("I1", "Never sell more tickets than exist", not problems,
                        "; ".join(problems) or f"{len(pairs)} confirmed, {len(holders)} in /status, total {total}"))

    # I2 -- never issue the same ticket number twice.
    per_ticket_status = defaultdict(set)
    for h in holders:
        per_ticket_status[h["ticket_no"]].add(h["user_id"])
    status_dupes = {t: sorted(u) for t, u in per_ticket_status.items() if len(u) > 1}
    status_rows_dupe = len(holders) - len({h["ticket_no"] for h in holders})
    per_ticket_client = defaultdict(set)
    for user, t in pairs:
        per_ticket_client[t].add(user)
    client_dupes = {t: sorted(u) for t, u in per_ticket_client.items() if len(u) > 1}
    problems = []
    if status_rows_dupe:
        problems.append(f"/status has {status_rows_dupe} repeated ticket numbers")
    if client_dupes:
        problems.append(f"{len(client_dupes)} ticket numbers confirmed to more than one user")
    examples = [{"ticket_no": t, "users": u} for t, u in list((client_dupes or status_dupes).items())[:EXAMPLES]]
    checks.append(Check("I2", "Never issue the same ticket number twice", not problems,
                        "; ".join(problems) or "every ticket number has exactly one holder", examples))

    # I3 -- the same request_id never yields two tickets.
    per_rid = defaultdict(set)
    for a in confirmed:
        per_rid[a.request_id].add(a.ticket_no)
    multi = {r: sorted(t) for r, t in per_rid.items() if len(t) > 1}
    dup_rids = sum(1 for a in attempts if a.kind in REPEATS)
    checks.append(Check("I3", "A repeated request_id gets one ticket, not two", not multi,
                        f"{len(multi)} request_ids received more than one ticket" if multi
                        else f"{dup_rids} duplicate/replayed requests, none produced a second ticket",
                        [{"request_id": r, "tickets": t} for r, t in list(multi.items())[:EXAMPLES]]))

    # I4 -- the count in /status matches the tickets actually issued.
    phantoms = sorted(pairs - status_pairs)
    problems = []
    if sold != len(holders):
        problems.append(f"/status sold={sold} but lists {len(holders)} holders")
    if phantoms:
        problems.append(f"{len(phantoms)} tickets confirmed to buyers are missing from /status (phantoms = lost sales)")
    checks.append(Check("I4", "/status count matches the tickets actually issued", not problems,
                        "; ".join(problems) or f"sold={sold} = {len(holders)} holders, every confirmed ticket present",
                        [{"user_id": u, "ticket_no": t} for u, t in phantoms[:EXAMPLES]]))

    # --- Beyond the four invariants -------------------------------------------------

    per_user = defaultdict(set)
    for user, t in pairs | status_pairs:
        per_user[user].add(t)
    greedy = {u: sorted(t) for u, t in per_user.items() if len(t) > 1}
    checks.append(Check("U1", "One ticket per user (product rule D3)", not greedy,
                        f"{len(greedy)} users hold more than one ticket" if greedy else "no user holds two tickets",
                        [{"user_id": u, "tickets": t} for u, t in list(greedy.items())[:EXAMPLES]]))

    # A request_id is "bound" once it has been confirmed a ticket. Reusing a bound
    # id as another user must be refused; an id that only ever got "sold out"
    # holds nothing, so there is nothing to conflict with.
    # The violation is the conflicting user being *given a ticket* (200). A 503 or
    # timeout is no answer at all -- neither acceptance nor rejection -- so it is
    # counted as undecided, not as a failure. (The first version failed U2 on shed
    # 503s under M6 load shedding.) Retries of a conflict probe count too.
    probe_keys = {(a.user_id, a.request_id) for a in attempts if a.kind == RID_CONFLICT}
    # Owner of each request_id, from confirmations that are not the probes' own
    # (including their retries -- otherwise a leaked ticket would rebind the id).
    bound = {a.request_id: a.user_id for a in confirmed if (a.user_id, a.request_id) not in probe_keys}
    conflict_keys = {(u, r) for u, r in probe_keys if bound.get(r, u) != u}
    conflict_attempts = [a for a in attempts if (a.user_id, a.request_id) in conflict_keys]
    leaked = [a for a in conflict_attempts if a.status == 200]
    rejected = {(a.user_id, a.request_id) for a in conflict_attempts if a.status == 422}
    other_definite = {(a.user_id, a.request_id) for a in conflict_attempts
                      if a.status not in (0, 200, 422, 503)} - rejected
    undecided = len(conflict_keys - rejected - other_definite - {(a.user_id, a.request_id) for a in leaked})
    checks.append(Check("U2", "A winner's request_id reused by another user is never given a ticket (422)",
                        not leaked if conflict_keys else None,
                        f"{len(leaked)} conflicting requests were given a ticket" if leaked
                        else f"{len(conflict_keys)} conflicting requests: {len(rejected)} rejected (422), "
                             f"{len(other_definite)} refused otherwise (e.g. 409), "
                             f"{undecided} never got a definite answer (503/timeout), 0 given a ticket",
                        [{"request_id": a.request_id, "user_id": a.user_id, "status": a.status, "ticket_no": a.ticket_no}
                         for a in leaked[:EXAMPLES]]))

    sold_out_answers = sum(1 for a in attempts if a.status == 409)
    false_sold_out = sold_out_answers > 0 and len(holders) < total
    checks.append(Check("U3", "Nobody is told 'sold out' while tickets remain", not false_sold_out,
                        f"{sold_out_answers} sold-out answers but only {len(holders)}/{total} tickets were issued"
                        if false_sold_out else f"{sold_out_answers} sold-out answers, {len(holders)}/{total} issued"))

    epochs = {a.epoch for a in attempts if a.epoch is not None}
    stale = epochs - {status.get("epoch")}
    checks.append(Check("U4", "Every response belongs to this sale (no reset mid-run)", not stale,
                        f"responses from other epochs: {sorted(stale)}" if stale else f"all responses epoch {status.get('epoch')}"))

    # A buyer who holds a ticket -- by this request_id, or as this user (D7) --
    # must get it back, never "sold out". Includes a twin that loses the race
    # for the very last ticket to its own duplicate.
    holds = {a.user_id for a in confirmed}
    denied = [a for a in attempts if a.status == 409 and a.user_id in holds]
    checks.append(Check("U5", "A buyer who holds a ticket is never told 'sold out'", not denied,
                        f"{len(denied)} requests from ticket holders were answered 'sold out'" if denied
                        else f"{sum(1 for a in attempts if a.user_id in holds and a.kind != FRESH)} repeat requests "
                             f"from holders, none told 'sold out'",
                        [{"user_id": a.user_id, "request_id": a.request_id, "kind": a.kind} for a in denied[:EXAMPLES]]))

    if audit is not None:
        # I4 says "always": the live auditor checked every snapshot during the sale.
        found = dict(audit.violations)
        checks.append(Check("A3", "Live audit: invariants held in every /status snapshot during the sale",
                            not found if audit.snapshots else None,
                            f"{sum(found.values())} violations in {audit.snapshots} snapshots: {found}" if found
                            else f"{audit.snapshots} snapshots over {audit.duration_s:.1f}s, 0 violations"
                                 + (f" ({audit.failed_polls} polls got no answer)" if audit.failed_polls else ""),
                            audit.examples))

    orphans = sorted(status_pairs - pairs)
    checks.append(Check("A2", "Orphaned tickets (sold, but the buyer was never told)", None,
                        f"{len(orphans)} tickets in /status were never confirmed to their buyer",
                        [{"user_id": u, "ticket_no": t} for u, t in orphans[:EXAMPLES]]))
    return checks


CORE = ("I1", "I2", "I3", "I4", "A3")  # A3 is I4's "always", checked live


def all_core_pass(checks: list[Check]) -> bool:
    return all(c.passed is not False for c in checks if c.id in CORE)
