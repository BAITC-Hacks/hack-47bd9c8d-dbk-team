#!/usr/bin/env bash
# One-time hackathon setup. Run in a NORMAL shell (not the Codex sandbox —
# needs write access to ~/.gbrain, ~/.agents, ~/.claude).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

echo "== 1/4 gbrain: deepseek chat/expansion via Baiterek"
# BRIDGE_BASE is exported by dev-workflow-setup.sh;
# standalone runs fall back to the local bridge from .env
BRIDGE="${BRIDGE_BASE:-$LITELLM_BASE_URL}"
gbrain config set sync.write_through off
gbrain config set expansion_model deepseek:deepseek-v4-1-flash
gbrain config set chat_model deepseek:deepseek-v4-1-flash
gbrain config set models.expansion deepseek:deepseek-v4-1-flash
gbrain config set models.chat deepseek:deepseek-v4-1-flash
gbrain config set models.default deepseek:deepseek-v4-1-flash
gbrain config set models.subagent deepseek:deepseek-v4-1-flash
gbrain config set provider_base_urls.deepseek "$BRIDGE"

echo "== 2/4 gbrain: embeddings qwen3-embedding-4b (rebuilds PGLite, auto-backup)"
gbrain config get embedding_model 2>/dev/null | grep -q qwen3-embedding-4b \
  || gbrain reinit-pglite --embedding-model litellm:qwen3-embedding-4b --embedding-dimensions 2560 --yes

echo "== 3/4 gbrain: compile context into AGENTS.md + keep it fresh on every sync"
gbrain compile-context --target codex --include tools/,decisions/
HOOK="$HOME/.claude/hooks/gbrain-sync.sh"
if ! grep -q compile-context "$HOOK"; then
  sed -i 's|^gbrain sync --repo "\$REPO" --no-embed </dev/null >/dev/null 2>&1 &$|( gbrain sync --repo "$REPO" \&\& cd "$REPO" \&\& gbrain compile-context --target codex --include tools/,decisions/ ) </dev/null >/dev/null 2>\&1 \&|' "$HOOK"
  # --no-embed dropped on purpose: embeddings are configured from step 2 on.
fi

echo "== 4/4 env for gbrain providers (~/.gbrain/.env — gbrain ignores cwd .env)"
GBENV="$HOME/.gbrain/.env"
touch "$GBENV"
sed -i '/^LITELLM_BASE_URL=/d;/^LITELLM_API_KEY=/d;/^DEEPSEEK_API_KEY=/d' "$GBENV"
printf 'LITELLM_BASE_URL=%s\nLITELLM_API_KEY=%s\nDEEPSEEK_API_KEY=%s\n' \
  "$BRIDGE" "$LITELLM_API_KEY" "$DEEPSEEK_API_KEY" >> "$GBENV"

echo "Done. Verify: gbrain query test && python3 tools/council.py --self-test (bridge must be up)"
