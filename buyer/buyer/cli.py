import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from . import auditor, coordinator, faults, report, runner, schedule, stats, verify


def _common(p: argparse.ArgumentParser, target_default: str) -> None:
    p.add_argument("--target", default=os.environ.get("BUYER_TARGET", target_default))
    p.add_argument("--processes", type=int, default=4, help="worker processes firing the stampede")
    p.add_argument("--max-inflight", type=int, default=2000,
                   help="open-loop cap on in-flight requests per process; waiting for a slot counts as client send lag")
    p.add_argument("--timeout", type=float, default=10.0, help="per-request client timeout, seconds")
    p.add_argument("--out", default="results")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="buyer", description="Load client that attacks the ticket seller and checks its invariants.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="reset the sale, fire the load, verify invariants, write a report")
    _common(r, "http://seller1:8000")
    r.add_argument("--scenario", default="adhoc", help="name used in the report and results folder")
    r.add_argument("--tickets", type=int, default=100)
    r.add_argument("--requests", type=int, default=50_000, help="distinct buyers, one fresh request each")
    r.add_argument("--burst", type=int, default=1_000, help="fresh requests all scheduled at t=0 (the on-sale moment)")
    r.add_argument("--rate", type=float, default=1_000, help="fresh requests per second after the burst")
    r.add_argument("--concurrency", type=int, default=None,
                   help="CLOSED-loop mode with this many in-flight requests (for the C4 comparison); "
                        "default is open-loop on the schedule")
    r.add_argument("--dup-concurrent", type=int, default=500, help="duplicates fired at the same instant as the original")
    r.add_argument("--dup-sequential", type=int, default=500, help="duplicates fired 50ms-1s after the original")
    r.add_argument("--replay-after", type=int, default=50, help="post-sale replays (~80%% of actual winners)")
    r.add_argument("--new-rid", type=int, default=20, help="winners retrying with a new request_id")
    r.add_argument("--rid-conflict", type=int, default=20, help="winners' request_ids reused by a different user")
    r.add_argument("--audit-interval", type=float, default=0.1, help="seconds between live /status audits; 0 disables")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--no-reset", action="store_true", help="do not POST /reset before the run")
    r.add_argument("--expect-allocator", help="refuse to run unless the seller reports this allocator "
                                              "(guards against attacking the wrong seller)")
    r.add_argument("--retry-unknown", type=int, default=0,
                   help="retry a 503/timeout up to N times with the SAME request_id (exponential backoff + jitter)")
    r.add_argument("--retry-rate", type=float, default=0,
                   help="retry budget: at most this many retries/s across the whole client (0 = unlimited); "
                        "over-budget retries wait, they are not dropped")
    f = r.add_argument_group("fault injection (toxiproxy; the buyer switches it on/off on its own clock)")
    f.add_argument("--stall-at", type=float, default=None, help="seconds after t0 to make the datastore slow")
    f.add_argument("--stall-for", type=float, default=10.0, help="how long it stays slow, seconds")
    f.add_argument("--stall-latency-ms", type=int, default=3000, help="added to every response from Postgres")
    f.add_argument("--toxiproxy", default="http://toxiproxy:8474", help="toxiproxy API")
    f.add_argument("--toxiproxy-proxy", default="postgres", help="name of the proxy in front of Postgres")
    f.add_argument("--fault-file", help="JSON written by an external fault script (scripts/killdb.sh) with "
                                        "wall-clock events; read after the stampede to place the fault on the timeline")

    c = sub.add_parser("calibrate", help="measure the client's own ceiling against a target that answers instantly")
    _common(c, "http://lb:8081")
    c.add_argument("--process-counts", default="1,2,4,8", help="comma-separated worker counts to try")
    c.add_argument("--concurrency-per-process", type=int, default=128,
                   help="closed-loop requests in flight per process while measuring the ceiling")
    c.add_argument("--duration", type=float, default=5.0, help="seconds of load per measurement")
    c.add_argument("--scenario", default="calibrate")

    m = sub.add_parser("compare", help="side-by-side table of saved run reports")
    m.add_argument("reports", nargs="+", help="result directories (or report.json files)")
    m.add_argument("--title", default="Comparison")
    m.add_argument("--write", help="also write the table to this file")
    m.add_argument("--timeline", action="store_true", help="append the runs' per-second timelines side by side")
    return p.parse_args(argv)


async def _post_reset(target: str, tickets: int) -> dict:
    async with aiohttp.ClientSession(base_url=target) as s:
        async with s.post("/reset", json={"count": tickets}) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                raise SystemExit(f"/reset failed: {resp.status} {body}")
            return body


async def _get_status(target: str, patience_s: float = 30.0) -> dict:
    """The final /status, retried for a while: after a fault the seller (or its
    database) may still be recovering, and verification needs one good read."""
    deadline = time.monotonic() + patience_s
    last = None
    async with aiohttp.ClientSession(base_url=target, timeout=aiohttp.ClientTimeout(total=10)) as s:
        while True:
            try:
                async with s.get("/status") as resp:
                    body = await resp.json(content_type=None)
                    if resp.status == 200:
                        return body
                    last = f"{resp.status} {body}"
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                last = repr(exc)
            if time.monotonic() > deadline:
                raise SystemExit(f"/status failed for {patience_s:.0f}s: {last}")
            await asyncio.sleep(1)


async def _get_metrics(target: str) -> dict:
    """Allocator counters from GET /metrics; {} if the target has none."""
    try:
        async with aiohttp.ClientSession(base_url=target, timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get("/metrics") as resp:
                return (await resp.json(content_type=None)).get("counters", {}) if resp.status == 200 else {}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {}


async def run(args: argparse.Namespace) -> int:
    started = datetime.now(timezone.utc)
    metrics_before = await _get_metrics(args.target)
    reset = None if args.no_reset else await _post_reset(args.target, args.tickets)
    if args.expect_allocator:
        actual = (reset or await _get_status(args.target)).get("allocator")
        if actual != args.expect_allocator:
            raise SystemExit(f"seller runs allocator {actual!r}, expected {args.expect_allocator!r}; refusing to run")

    spec = schedule.ScheduleSpec(
        requests=args.requests, rate=args.rate, burst=args.burst, tickets=args.tickets,
        dup_concurrent=args.dup_concurrent, dup_sequential=args.dup_sequential,
        replay_after=args.replay_after, new_rid=args.new_rid, rid_conflict=args.rid_conflict, seed=args.seed,
    )
    stop_audit = asyncio.Event()
    audit_task = (asyncio.create_task(auditor.audit(args.target, args.tickets, stop_audit, args.audit_interval))
                  if args.audit_interval > 0 else None)

    plan = schedule.build(spec)
    mode = f"closed-loop x{args.concurrency}" if args.concurrency else "open-loop"
    print(f"[buyer] phase 1: {len(plan)} requests, {mode}, {args.processes} processes -> {args.target}", file=sys.stderr)
    t0 = time.perf_counter() + coordinator.SPAWN_LEAD_S
    t0_wall = time.time() + (t0 - time.perf_counter())  # the same instant on the (container) wall clock
    fault_task = None
    if args.stall_at is not None:
        fault_task = asyncio.create_task(faults.latency_window(
            args.toxiproxy, args.toxiproxy_proxy, t0, args.stall_at, args.stall_for, args.stall_latency_ms))
    stampede, workers, t0 = await coordinator.run_phase(args.target, plan, args.processes, args.timeout,
                                                        args.concurrency, args.max_inflight,
                                                        retries=args.retry_unknown, retry_rate=args.retry_rate, t0=t0)
    fault = await fault_task if fault_task else None
    if args.fault_file:
        fault = faults.external_window(args.fault_file, t0_wall) or fault
    if fault:
        print(f"[buyer] fault: {fault}", file=sys.stderr)

    probes_plan = schedule.build_probes(spec, stampede)
    print(f"[buyer] phase 2: {len(probes_plan)} probes aimed at actual winners/losers", file=sys.stderr)
    probes = await runner.run_open_loop(args.target, probes_plan, time.perf_counter() + 0.1, args.timeout,
                                        retries=args.retry_unknown)
    attempts = stampede + probes

    stop_audit.set()
    audit = await audit_task if audit_task else None
    status = await _get_status(args.target)
    checks = verify.verify(status, attempts, total=args.tickets, audit=audit)
    summary = stats.summarize(stampede, t0, workers)  # load numbers: the stampede only
    summary["probes"] = len(probes)
    if fault and fault.actual_start_s is not None:
        summary["at_fault"] = stats.inflight_at(attempts, t0 + fault.actual_start_s)
    metrics_after = await _get_metrics(args.target)
    summary["server_counters"] = {k: v - metrics_before.get(k, 0) for k, v in metrics_after.items()
                                  if v - metrics_before.get(k, 0)}

    meta = {
        "scenario": args.scenario,
        "target": args.target,
        "allocator": status.get("allocator") or (reset or {}).get("allocator"),
        "mode": mode,
        "processes": args.processes,
        "tickets": args.tickets,
        "requests": args.requests,
        "burst": args.burst,
        "rate": args.rate,
        "seed": args.seed,
        "started_utc": started.isoformat(timespec="seconds"),
        "retry_unknown": args.retry_unknown,
        "retry_rate": args.retry_rate,
        "fault": dataclasses.asdict(fault) if fault else None,
        "args": vars(args),
    }
    out_dir = Path(args.out) / f"{started:%Y%m%dT%H%M%SZ}-{args.scenario}"
    report.write(out_dir, meta, summary, checks, status, attempts)
    print(report.render_markdown(meta, summary, checks))
    print(f"[buyer] report written to {out_dir}", file=sys.stderr)
    return 0 if verify.all_core_pass(checks) else 1


async def calibrate(args: argparse.Namespace) -> int:
    """Same client code, against a target that does no work (nginx returning a canned
    response). Step 1, per process count: closed-loop for `duration` seconds; the rate
    it reaches is the client's ceiling (the target never stalls, so closed-loop hides
    nothing here). Step 2: open-loop at half the best ceiling, to show that at that
    rate the client keeps its schedule (send lag stays near zero)."""
    started = datetime.now(timezone.utc)
    counts = [int(x) for x in args.process_counts.split(",")]
    enough = int(100_000 * args.duration)  # more requests than any process count can send in `duration`
    backlog = schedule.build(schedule.ScheduleSpec(requests=enough, rate=1, burst=enough, tickets=0))
    rows = []
    for procs in counts:
        conc = args.concurrency_per_process * procs
        print(f"[calibrate] ceiling: {procs} processes, closed-loop x{conc}, {args.duration}s ...", file=sys.stderr)
        attempts, workers, t0 = await coordinator.run_phase(args.target, backlog, procs, args.timeout,
                                                            concurrency=conc, duration=args.duration)
        s = stats.summarize(attempts, t0, workers)
        rows.append({"mode": f"closed-loop x{conc}", "processes": procs, **s})
        print(f"[calibrate]   -> {s['throughput_rps']} req/s, worker CPU max {s['client']['cpu_util_max']:.0%}",
              file=sys.stderr)

    best = max(rows, key=lambda r: r["throughput_rps"])
    rate = round(best["throughput_rps"] / 2, -2)
    procs = best["processes"]
    print(f"[calibrate] validation: open-loop at {rate:.0f} req/s with {procs} processes ...", file=sys.stderr)
    plan = schedule.build(schedule.ScheduleSpec(requests=int(rate * args.duration), rate=rate, burst=0, tickets=0))
    attempts, workers, t0 = await coordinator.run_phase(args.target, plan, procs, args.timeout,
                                                        max_inflight=args.max_inflight)
    s = stats.summarize(attempts, t0, workers)
    rows.append({"mode": f"open-loop @ {rate:.0f}/s", "processes": procs, **s})

    out_dir = Path(args.out) / f"{started:%Y%m%dT%H%M%SZ}-{args.scenario}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"scenario": args.scenario, "target": args.target, "started_utc": started.isoformat(timespec="seconds"),
            "duration_s": args.duration, "concurrency_per_process": args.concurrency_per_process}
    (out_dir / "report.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=2))
    md = report.render_calibration(meta, rows)
    (out_dir / "report.md").write_text(md)
    print(md)
    print(f"[calibrate] report written to {out_dir}", file=sys.stderr)
    return 0


def compare(args: argparse.Namespace) -> int:
    loaded = []
    for r in args.reports:
        path = Path(r)
        path = path / "report.json" if path.is_dir() else path
        loaded.append((path.parent.name, json.loads(path.read_text())))
    md = report.render_comparison(args.title, loaded)
    if args.timeline:
        md += report.render_timelines_side_by_side(loaded)
    print(md)
    if args.write:
        Path(args.write).write_text(md)
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "compare":
        return compare(args)
    if args.command == "run":
        return asyncio.run(run(args))
    if args.command == "calibrate":
        return asyncio.run(calibrate(args))
    return 2
