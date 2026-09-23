#!/usr/bin/env bash
# Local Responses->Chat bridge for Codex CLI. Port 4000.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
exec uvx --python 3.12 --from 'litellm[proxy]' litellm --config tools/litellm.yaml --port 4000 "$@"
