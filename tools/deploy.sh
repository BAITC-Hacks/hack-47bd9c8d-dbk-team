#!/usr/bin/env bash
# Deploy to docker-server: git pull + restart app on :8181 → https://app.aibots.kz
# Requires: ~/.ssh/config alias docker-server-access (see tools/dev-workflow/ssh-config),
# your key in the server's authorized_keys, cloudflared installed locally.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export CLOUDFLARE_ACCESS_CLIENT_ID="${CLOUDFLARE_ACCESS_CLIENT_ID:-$CLOUDFLARE_CLIENT_ID}"
export CLOUDFLARE_ACCESS_CLIENT_SECRET="${CLOUDFLARE_ACCESS_CLIENT_SECRET:-$CLOUDFLARE_CLIENT_SECRET}"

ssh -o BatchMode=yes docker-server-access '
  cd ~/dbk && git pull --ff-only &&
  if [ -f docker-compose.yml ]; then
    docker compose up -d --build
  else
    echo "no docker-compose.yml yet — pulled only"
  fi'
