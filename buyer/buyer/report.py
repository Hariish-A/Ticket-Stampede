import json
from pathlib import Path

from .verify import Check


def _ms(v) -> str:
    return "-" if v is None else f"{v:.1f}"


def render_markdown(meta: dict, stats: dict, checks: list[Check]) -> str:
    lines = [f"# Run `{meta['scenario']}`", ""]
    lines.append(
        f"target `{meta['target']}` · allocator **{meta.get('allocator', '?')}** · "
        f"{meta.get('mode', 'open-loop')}, {meta.get('processes', 1)} processes · "
        f"{meta['tickets']} tickets · {stats['requests_sent']} requests "
        f"(burst {meta['burst']} at t=0, then {meta['rate']}/s) · seed {meta['seed']} · {meta['started_utc']}"
    )
    lines += ["", "## Invariants", "", "| | Check | Verdict | Detail |", "|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c.id} | {c.name} | **{c.verdict}** | {c.detail} |")
    failing = [c for c in checks if c.passed is False and c.examples]
    if failing:
        lines += ["", "Examples of failures:", ""]
        for c in failing:
            lines.append(f"- {c.id}: `{json.dumps(c.examples[:3])}`")

    lines += ["", "## Throughput and latency", ""]
    lines.append(
        f"Stampede: {stats['responses']} responses in {stats['window_s']} s → **{stats['throughput_rps']} req/s** handled; "
        f"{stats['no_response']} without a response. Then {stats.get('probes', 0)} post-sale probes (verified, not timed)."
    )
    lines += ["", "| ms | p50 | p90 | p99 | max |", "|---|---|---|---|---|"]
    for key, label in (
        ("latency_ms", "latency (from scheduled send)"),
        ("service_ms", "service time (from actual send)"),
        ("send_lag_ms", "client send lag"),
    ):
        d = stats[key]
        lines.append(f"| {label} | {_ms(d['p50'])} | {_ms(d['p90'])} | {_ms(d['p99'])} | {_ms(d['max'])} |")
    srv = stats.get("server_ms") or {}
    if srv.get("handler", {}).get("count"):
        for key, label in (
            ("acq", "↳ seller: waiting for a DB connection"),
            ("alloc", "↳ seller: allocator queries"),
            ("handler", "↳ seller: whole handler"),
            ("outside_handler", "↳ outside the handler (HTTP, event-loop queue, network)"),
        ):
            d = srv[key]
            lines.append(f"| {label} | {_ms(d['p50'])} | {_ms(d['p90'])} | {_ms(d['p99'])} | {_ms(d['max'])} |")
    lines += ["", f"Responses by HTTP status: `{stats['by_status']}`  "]
    lines.append(f"Requests by kind: `{stats['by_kind']}`  ")
    if stats["errors"]:
        lines.append(f"Transport errors: `{stats['errors']}`  ")
    lines.append(f"First sold-out answer at t = {stats['first_sold_out_at_s']} s  ")
    if stats.get("server_counters"):
        lines.append(f"Seller counters during the run (GET /metrics): `{stats['server_counters']}`  ")
    client = stats.get("client") or {}
    if client.get("processes"):
        lines.append(f"Client health: {client['processes']} worker processes, CPU per worker "
                     f"`{[f'{u:.0%}' for u in client['cpu_util_per_worker']]}` of one core; "
                     f"send lag p99 {_ms(stats['send_lag_ms']['p99'])} ms. "
                     f"A worker near 100% or a growing send lag means the client, not the seller, was the limit.")
    return "\n".join(lines) + "\n"


def render_comparison(title: str, loaded: list[tuple[str, dict]]) -> str:
    """One row per saved run: correctness first, then speed, then what the seller had to do."""
    lines = [f"# {title}", "",
             "| run | allocator | tickets | invariants | req/s | p50 ms | p99 ms | max ms | 503s | sold out at s "
             "| seller counters | client lag p99 ms |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in loaded:
        meta, st, checks = r["meta"], r["stats"], r["checks"]
        failed = [c["id"] for c in checks if c["verdict"] == "FAIL"]
        verdict = "all PASS" if not failed else "FAIL: " + ", ".join(failed)
        counters = ", ".join(f"{k}={v}" for k, v in sorted((st.get("server_counters") or {}).items())) or "-"
        lat = st["latency_ms"]
        lines.append(f"| {name} | {meta.get('allocator')} | {meta.get('tickets')} | {verdict} | "
                     f"{st['throughput_rps']} | {_ms(lat['p50'])} | {_ms(lat['p99'])} | {_ms(lat['max'])} | "
                     f"{st['by_status'].get('503', 0)} | {st.get('first_sold_out_at_s')} | {counters} | "
                     f"{_ms(st['send_lag_ms']['p99'])} |")
    lines += ["", "Latency is measured from each request's scheduled send time (open-loop). "
                  "'sold out at' = seconds from the start until the first sold-out answer, i.e. how long selling "
                  "every ticket took. Seller counters come from GET /metrics, diffed across the run."]
    return "\n".join(lines) + "\n"


def write(out_dir: Path, meta: dict, stats: dict, checks: list[Check], status: dict, attempts) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "meta": meta,
        "stats": stats,
        "checks": [c.__dict__ | {"verdict": c.verdict} for c in checks],
        "status": status,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "report.md").write_text(render_markdown(meta, stats, checks))
    with (out_dir / "ledger.jsonl").open("w") as f:
        for a in attempts:
            f.write(json.dumps(a.as_dict()) + "\n")
    return out_dir


def render_calibration(meta: dict, rows: list[dict]) -> str:
    lines = [f"# Client calibration `{meta['scenario']}`", "",
             f"Target `{meta['target']}` answers every request with a canned response and does no other work, "
             f"so these numbers are the ceiling of the **client**, not of any seller. "
             f"{meta['duration_s']} s per row. {meta['started_utc']}", "",
             "| mode | processes | achieved req/s | send lag p50 ms | send lag p99 ms | latency p99 ms | worker CPU (max) | no response |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['mode']} | {r['processes']} | **{r['throughput_rps']}** | {_ms(r['send_lag_ms']['p50'])} | "
                     f"{_ms(r['send_lag_ms']['p99'])} | {_ms(r['latency_ms']['p99'])} | "
                     f"{r['client']['cpu_util_max']:.0%} | {r['no_response']} |")
    lines += ["", "Closed-loop rows measure the ceiling (send lag is 0 by construction there). The open-loop row "
                  "checks that at half the best ceiling the client keeps its schedule."]
    return "\n".join(lines) + "\n"
