"""Summarise a py-spy `--format raw` profile of the seller by layer.

    python -m buyer.profile_report pyspy-raw.txt <sample_hz> <seconds>

Each line is a collapsed stack `frame;frame;...;leaf N`. Samples are only taken
while the thread is running (not idle in epoll), so samples / (hz * seconds)
is how busy the seller's one Python thread was. "Self" time is attributed to
the leaf frame's layer; "inclusive" counts every stack a layer appears in.
"""

import re
import sys
from collections import Counter

LAYERS = [  # first match wins; matched against the frame's file path
    ("DB driver (asyncpg)", re.compile(r"asyncpg")),
    ("HTTP server (uvicorn/httptools)", re.compile(r"uvicorn|httptools|h11")),
    ("framework & validation (FastAPI/Starlette/Pydantic)", re.compile(r"fastapi|starlette|pydantic|anyio")),
    ("JSON", re.compile(r"json")),
    ("our code (app/)", re.compile(r"/srv/app/|\bapp/")),
    ("event loop (asyncio/uvloop)", re.compile(r"asyncio|uvloop")),
]
FRAME = re.compile(r"^(?P<func>.*?) \((?P<file>[^:()]+)(?::\d+)?\)$")


def layer_of(frame: str) -> str:
    m = FRAME.match(frame.strip())
    path = m.group("file") if m else frame
    for name, rx in LAYERS:
        if rx.search(path):
            return name
    return "other (stdlib, logging, ...)"


def main(argv: list[str]) -> int:
    path, hz, seconds = argv[0], float(argv[1]), float(argv[2])
    self_by_layer, incl_by_layer, leaves = Counter(), Counter(), Counter()
    total = 0
    for line in open(path, encoding="utf-8", errors="replace"):
        stack, _, count = line.rstrip().rpartition(" ")
        if not stack or not count.isdigit():
            continue
        n = int(count)
        frames = [f for f in stack.split(";") if f and not f.startswith(("process ", "thread "))]
        if not frames:
            continue
        total += n
        self_by_layer[layer_of(frames[-1])] += n
        for layer in {layer_of(f) for f in frames}:
            incl_by_layer[layer] += n
        leaves[frames[-1].strip()] += n

    busy = total / (hz * seconds) if hz and seconds else 0
    lines = ["# Seller CPU profile (py-spy)", "",
             f"{total} samples at {hz:.0f} Hz over {seconds:.0f} s → the seller's Python thread was busy "
             f"**{busy:.0%}** of the time (100% = one core saturated).", "",
             "| layer | self (leaf) | inclusive |", "|---|---|---|"]
    for layer, n in self_by_layer.most_common():
        lines.append(f"| {layer} | {n / total:.0%} | {incl_by_layer[layer] / total:.0%} |")
    lines += ["", "Top leaf frames:", "", "| share | frame |", "|---|---|"]
    for frame, n in leaves.most_common(12):
        lines.append(f"| {n / total:.1%} | `{frame[:110]}` |")
    print("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
