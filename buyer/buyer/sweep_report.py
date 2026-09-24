"""Summarise a rate sweep: one row per offered rate, joining three independent
sources of evidence for where the time goes:

  1. the buyer's report      -- latency, 503s, Server-Timing breakdown, client health
  2. container CPU samples   -- `docker stats` for seller1 and postgres
  3. Postgres wait samples   -- pg_stat_activity: is the database busy, or idle
                                waiting for the application?

    python -m buyer.sweep_report <sweep_dir> <run_dir> [<run_dir> ...]

The sweep dir holds cpu-<rate>.txt and pgwait-<rate>.txt from scripts/sweep.sh.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _ms(v) -> str:
    return "-" if v is None else f"{v:.1f}"


def cpu_by_group(path: Path) -> dict[str, tuple[float, float]]:
    """{group: (mean %, max %)} where 100% = one core. Groups: "sellers" (all
    seller instances summed per sample -- one for M5, three for M8), "postgres",
    "lb" (nginx). Samples come from one `docker stats` pass per timestamp."""
    per_pass: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) < 3 or not parts[2].endswith("%"):
                continue
            try:
                pct = float(parts[2].rstrip("%"))
            except ValueError:
                continue
            name = parts[1]
            group = ("sellers" if "seller" in name and "tests" not in name else
                     "postgres" if "postgres" in name else "lb" if "-lb-" in name else None)
            if group:
                per_pass[parts[0]][group] += pct
    out = {}
    for group in ("sellers", "postgres", "lb"):
        v = [p[group] for p in per_pass.values() if group in p]
        if v:
            out[group] = (sum(v) / len(v), max(v))
    return out


def pg_waits(path: Path) -> tuple[float, float, list[tuple[str, float]]]:
    """(mean active backends, mean idle backends, top wait events of active backends as share)."""
    polls, active, idle, events = 0, 0, 0, Counter()
    if path.exists():
        for block in path.read_text().split("--\n"):
            rows = [r.split("|") for r in block.strip().splitlines() if r.count("|") == 2]
            if not block.strip():
                continue
            polls += 1
            for state, etype, event in rows:
                if state == "active":
                    active += 1
                    events[f"{etype}:{event}" if etype else "running (no wait = on CPU)"] += 1
                elif state.startswith("idle"):
                    idle += 1
    if not polls:
        return 0.0, 0.0, []
    total_active = sum(events.values()) or 1
    return active / polls, idle / polls, [(e, n / total_active) for e, n in events.most_common(3)]


def main(argv: list[str]) -> int:
    sweep_dir, run_dirs = Path(argv[0]), [Path(p) for p in argv[1:]]
    rows = []
    for d in run_dirs:
        r = json.loads((d / "report.json").read_text())
        rate = int(r["meta"]["rate"])
        st = r["stats"]
        cpu = cpu_by_group(sweep_dir / f"cpu-{rate}.txt")
        seller, pg, lb = (cpu.get(g, (0.0, 0.0)) for g in ("sellers", "postgres", "lb"))
        active, idle, waits = pg_waits(sweep_dir / f"pgwait-{rate}.txt")
        failed = [c["id"] for c in r["checks"] if c["verdict"] == "FAIL"]
        rows.append(dict(rate=rate, st=st, seller=seller, pg=pg, lb=lb, active=active, idle=idle, waits=waits,
                         failed=failed, target=r["meta"]["target"]))
    rows.sort(key=lambda x: x["rate"])

    # Baseline = the best p99 of any step, not the first step's: the first step
    # can include a cold start (fresh container, pool growing) and inflate it.
    base_p99 = min((x["st"]["latency_ms"]["p99"] for x in rows), default=None)
    knee = None
    for x in rows:
        st = x["st"]
        errors = st["by_status"].get("503", 0) + st["no_response"]
        degraded = (st["latency_ms"]["p99"] > 3 * base_p99 + 10 or errors > 0.001 * st["requests_sent"]
                    or st["throughput_rps"] < 0.95 * x["rate"])
        if degraded and knee is None:
            knee = x["rate"]
        x["errors"] = errors

    target = rows[0]["target"] if rows else "?"
    lines = ["# Rate sweep: where does latency degrade, and why?", "",
             f"Target `{target}`. Steady open-loop load on the sold-out path (100 tickets, sold out in the first "
             "moments), one row per offered rate. CPU: 100% = one core. Each seller instance is one Python process "
             "(one uvicorn worker, D11), so ~100% per instance is its ceiling; 'sellers CPU' sums all instances.", "",
             "| offered/s | handled/s | p50 ms | p99 ms | 503+lost | acq p50/p99 | alloc p50/p99 | outside handler p50/p99 "
             "| sellers CPU mean/max | postgres CPU mean/max | nginx CPU mean/max | PG active/idle conns | PG top waits (active) "
             "| client lag p99 | invariants |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in rows:
        st, srv = x["st"], x["st"].get("server_ms", {})
        waits = "; ".join(f"{e} {share:.0%}" for e, share in x["waits"]) or "-"
        mark = " **← knee**" if x["rate"] == knee else ""
        lines.append(
            f"| {x['rate']}{mark} | {st['throughput_rps']} | {_ms(st['latency_ms']['p50'])} | {_ms(st['latency_ms']['p99'])} "
            f"| {x['errors']} | {_ms(srv.get('acq', {}).get('p50'))}/{_ms(srv.get('acq', {}).get('p99'))} "
            f"| {_ms(srv.get('alloc', {}).get('p50'))}/{_ms(srv.get('alloc', {}).get('p99'))} "
            f"| {_ms(srv.get('outside_handler', {}).get('p50'))}/{_ms(srv.get('outside_handler', {}).get('p99'))} "
            f"| {x['seller'][0]:.0f}%/{x['seller'][1]:.0f}% | {x['pg'][0]:.0f}%/{x['pg'][1]:.0f}% "
            f"| {x['lb'][0]:.0f}%/{x['lb'][1]:.0f}% "
            f"| {x['active']:.1f}/{x['idle']:.1f} | {waits} | {_ms(st['send_lag_ms']['p99'])} "
            f"| {'all PASS' if not x['failed'] else 'FAIL: ' + ','.join(x['failed'])} |")
    lines += ["", f"Knee (first rate with p99 > 3x the best step's p99, >0.1% errors, or <95% of offered handled): "
                  f"**{knee if knee else 'not reached'}**"]
    md = "\n".join(lines) + "\n"
    (sweep_dir / "summary.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
