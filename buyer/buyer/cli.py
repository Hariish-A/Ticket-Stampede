import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from . import report, runner, schedule, stats, verify


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="buyer", description="Load client that attacks the ticket seller and checks its invariants.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="reset the sale, fire the load, verify invariants, write a report")
    r.add_argument("--target", default=os.environ.get("BUYER_TARGET", "http://seller1:8000"))
    r.add_argument("--scenario", default="adhoc", help="name used in the report and results folder")
    r.add_argument("--tickets", type=int, default=100)
    r.add_argument("--requests", type=int, default=50_000, help="distinct buyers, one fresh request each")
    r.add_argument("--burst", type=int, default=1_000, help="fresh requests all scheduled at t=0 (the on-sale moment)")
    r.add_argument("--rate", type=float, default=1_000, help="fresh requests per second after the burst")
    r.add_argument("--dup-concurrent", type=int, default=500, help="duplicates fired at the same instant as the original")
    r.add_argument("--dup-sequential", type=int, default=500, help="duplicates fired 50ms-1s after the original")
    r.add_argument("--replay-after", type=int, default=50, help="replays of early (likely winning) requests after sell-out")
    r.add_argument("--new-rid", type=int, default=20, help="early users retrying with a new request_id")
    r.add_argument("--rid-conflict", type=int, default=20, help="early request_ids reused by a different user")
    r.add_argument("--timeout", type=float, default=10.0, help="per-request client timeout, seconds")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", default="results")
    r.add_argument("--no-reset", action="store_true", help="do not POST /reset before the run")
    return p.parse_args(argv)


async def _post_reset(target: str, tickets: int) -> dict:
    async with aiohttp.ClientSession(base_url=target) as s:
        async with s.post("/reset", json={"count": tickets}) as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                raise SystemExit(f"/reset failed: {resp.status} {body}")
            return body


async def _get_status(target: str) -> dict:
    async with aiohttp.ClientSession(base_url=target) as s:
        async with s.get("/status") as resp:
            body = await resp.json(content_type=None)
            if resp.status != 200:
                raise SystemExit(f"/status failed: {resp.status} {body}")
            return body


async def run(args: argparse.Namespace) -> int:
    started = datetime.now(timezone.utc)
    reset = None if args.no_reset else await _post_reset(args.target, args.tickets)

    plan = schedule.build(schedule.ScheduleSpec(
        requests=args.requests, rate=args.rate, burst=args.burst, tickets=args.tickets,
        dup_concurrent=args.dup_concurrent, dup_sequential=args.dup_sequential,
        replay_after=args.replay_after, new_rid=args.new_rid, rid_conflict=args.rid_conflict, seed=args.seed,
    ))
    print(f"[buyer] firing {len(plan)} requests at {args.target} ...", file=sys.stderr)
    attempts, t0 = await runner.run_open_loop(args.target, plan, timeout=args.timeout)

    status = await _get_status(args.target)
    checks = verify.verify(status, attempts, total=args.tickets)
    summary = stats.summarize(attempts, t0)

    meta = {
        "scenario": args.scenario,
        "target": args.target,
        "allocator": status.get("allocator") or (reset or {}).get("allocator"),
        "tickets": args.tickets,
        "requests": args.requests,
        "burst": args.burst,
        "rate": args.rate,
        "seed": args.seed,
        "started_utc": started.isoformat(timespec="seconds"),
        "args": vars(args),
    }
    out_dir = Path(args.out) / f"{started:%Y%m%dT%H%M%SZ}-{args.scenario}"
    report.write(out_dir, meta, summary, checks, status, attempts)
    print(report.render_markdown(meta, summary, checks))
    print(f"[buyer] report written to {out_dir}", file=sys.stderr)
    return 0 if verify.all_core_pass(checks) else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "run":
        return asyncio.run(run(args))
    return 2
