#!/usr/bin/env bash
# Unit tests (verifier + schedule), run inside the buyer image so no local Python setup is needed.
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
docker compose build buyer >/dev/null
docker compose run --rm --no-deps --entrypoint python buyer -m pytest -q tests "$@"
