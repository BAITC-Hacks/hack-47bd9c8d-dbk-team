#!/usr/bin/env bash
# DBK dev-workflow bootstrap — bare machine with Codex CLI to full stack.
# Idempotent. Run: bash tools/dev-workflow-setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 0/8 prereqs"
MISSING=()
for c in codex git uv node npm bun; do command -v "$c" >/dev/null 2>&1 || MISSING+=("$c"); done
if ((${#MISSING[@]})); then
  echo "Missing: ${MISSING[*]}"
  echo "bun: curl -fsSL https://bun.sh/install | bash   uv: curl -fsSL https://astral.sh/uv/install.sh | bash"
  exit 1
fi

echo "== 1/8 .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  created .env from example — FILL IN THE KEYS, then re-run this script"
  exit 1
fi
set -a; . ./.env; set +a

echo "== 1b/8 network: Baiterek reachability"
if curl -s -o /dev/null --max-time 6 https://llm.baiterek.gov.kz/v1/models -H "Authorization: Bearer $BAITEREK_LLM_GATEWAY_API_KEY"; then
  BRIDGE_BASE="http://127.0.0.1:4000/v1"; DIRECT_PROVIDER="baiterek"
  echo "  Baiterek reachable — local bridge"
else
  BRIDGE_BASE="http://127.0.0.1:4000/v1"; DIRECT_PROVIDER="baiterek"
  echo "  WARNING: Baiterek unreachable from this machine."
  echo "  Corporate models unavailable here — use the issued OpenAI key via codex."
fi
export BRIDGE_BASE

echo "== 2/8 skill packs (gsd, gstack, impeccable)"
[ -d "$HOME/.codex/gsd-core" ] || npx @opengsd/gsd-core@latest --codex --global
if [ ! -d tools/gstack ]; then
  git clone --depth 1 https://github.com/garrytan/gstack tools/gstack
fi
[ -d "$HOME/.codex/skills/gstack" ] || (cd tools/gstack && BUN_TMPDIR=/tmp/bun-tmp ./setup --host codex)
npx impeccable install --providers=codex --scope=global || true

echo "== 3/8 codex profiles"
cat > "$HOME/.codex/glm-flash.config.toml" <<'TOML'
model_provider = "bridge"
model = "glm-5.3-flash"
model_reasoning_effort = "high"
TOML
cat > "$HOME/.codex/deepseek.config.toml" <<TOML
model_context_window = 265000
model_provider = "$DIRECT_PROVIDER"
model = "deepseek-v4-1-flash"
model_reasoning_effort = "medium"
TOML
cat > "$HOME/.codex/kimi.config.toml" <<TOML
model_context_window = 1048576
model_provider = "$DIRECT_PROVIDER"
model = "kimi-k3"
model_reasoning_effort = "high"
TOML

echo "== 4/8 codex config.toml: providers + agents + MCP"
CFG="$HOME/.codex/config.toml"
touch "$CFG"
codex features enable multi_agent_v2 >/dev/null 2>&1 || true
grep -q 'model_providers.bridge' "$CFG" || cat >> "$CFG" <<TOML

[model_providers.bridge]
name = "LiteLLM bridge -> corporate gateways"
base_url = "$BRIDGE_BASE"
wire_api = "responses"

[model_providers.baiterek]
name = "Baiterek LLM gateway"
base_url = "https://llm.baiterek.gov.kz/v1"
env_key = "BAITEREK_LLM_GATEWAY_API_KEY"
wire_api = "responses"

[agents.coder]
description = "Fast implementer for well-specified tasks: write code, run tests, fix until green."
config_file = "deepseek.config.toml"

[agents.explorer]
description = "Read-only investigator: find files, trace call paths, summarize code."
config_file = "kimi.config.toml"
TOML
grep -q 'mcp_servers.gbrain' "$CFG" || cat >> "$CFG" <<'TOML'

[mcp_servers.gbrain]
command = "gbrain"
args = ["serve", "--surface", "verbs"]
TOML
grep -q 'mcp_servers.firecrawl' "$CFG" || cat >> "$CFG" <<TOML

[mcp_servers.firecrawl]
command = "npx"
args = ["-y", "firecrawl-mcp"]
env = { FIRECRAWL_API_KEY = "${FIRECRAWL_API_KEY:-REPLACE_ME}" }
TOML
grep -q 'mcp_servers.21st' "$CFG" || cat >> "$CFG" <<'TOML'

[mcp_servers.21st]
url = "https://21st.dev/api/mcp"
bearer_token_env_var = "API_KEY_21ST"
TOML
grep -q 'mcp_servers.context7' "$CFG" || cat >> "$CFG" <<TOML

[mcp_servers.context7]
type = "http"
url = "https://mcp.context7.com/mcp"

[mcp_servers.context7.http_headers]
Authorization = "Bearer ${CONTEXT7_API_KEY:-REPLACE_ME}"
TOML
grep -q 'mcp_servers.chrome-devtools' "$CFG" || cat >> "$CFG" <<'TOML'

[mcp_servers.chrome-devtools]
command = "npx"
args = ["-y", "chrome-devtools-mcp@latest"]
TOML

echo "== 5/8 hooks"
mkdir -p "$HOME/.claude/hooks"
cp tools/dev-workflow/gbrain-sync.sh "$HOME/.claude/hooks/gbrain-sync.sh"
chmod +x "$HOME/.claude/hooks/gbrain-sync.sh"
cp tools/dev-workflow/god-file-warn.py "$HOME/.claude/hooks/god-file-warn.py"
chmod +x "$HOME/.claude/hooks/god-file-warn.py"
# hooks.json travels via git/pack with the lead's home paths — retarget to THIS machine
[ -f .codex/hooks.json ] && sed -i "s|/home/sergey|$HOME|g" .codex/hooks.json
if [ -f "$HOME/.claude/settings.json" ] && ! grep -q gbrain-sync "$HOME/.claude/settings.json"; then
  cp "$HOME/.claude/settings.json" "$HOME/.claude/settings.json.bak-gbrain"
  node -e '
const fs = require("fs");
const p = process.env.HOME + "/.claude/settings.json";
const d = JSON.parse(fs.readFileSync(p, "utf8"));
(d.hooks ||= {}).PostToolUse ||= [];
d.hooks.PostToolUse.push({ matcher: "Bash", hooks: [{ type: "command", command: "bash \"$HOME/.claude/hooks/gbrain-sync.sh\"", timeout: 5, statusMessage: "Syncing brain" }] });
fs.writeFileSync(p, JSON.stringify(d, null, 2) + "\n");
'
fi
# repo .codex/hooks.json travels via git; normalize the gbrain entry to THIS machine
# (the committed file carries the lead's home path; impeccable manages its own entry)
[ -f .codex/hooks.json ] && node -e '
const fs = require("fs");
const p = ".codex/hooks.json";
const d = JSON.parse(fs.readFileSync(p, "utf8"));
const cmd = `[ ! -f "${process.env.HOME}/.claude/hooks/gbrain-sync.sh" ] || bash "${process.env.HOME}/.claude/hooks/gbrain-sync.sh"`;
d.hooks.PostToolUse = (d.hooks.PostToolUse || []).filter(g => !JSON.stringify(g).includes("gbrain-sync"));
d.hooks.PostToolUse.push({ matcher: "Bash|shell|exec_command|local_shell", hooks: [{ type: "command", command: cmd, timeout: 5, statusMessage: "Syncing brain" }] });
d.hooks.PostToolUse = d.hooks.PostToolUse.filter(g => !JSON.stringify(g).includes("god-file"));
d.hooks.PostToolUse.push({ matcher: "Edit|Write|apply_patch|Bash|shell|exec_command|local_shell", hooks: [{ type: "command", command: `[ ! -f "${process.env.HOME}/.claude/hooks/god-file-warn.py" ] || python3 "${process.env.HOME}/.claude/hooks/god-file-warn.py"`, timeout: 5, statusMessage: "God-file check" }] });
fs.writeFileSync(p, JSON.stringify(d, null, 2) + "\n");
console.log("gbrain hook entry normalized to", process.env.HOME);
' || true

echo "== 6/8 bashrc exports"
for line in \
  "export BAITEREK_LLM_GATEWAY_API_KEY=\"$BAITEREK_LLM_GATEWAY_API_KEY\"" \
  "export API_KEY_21ST=\"${API_KEY_21ST:-}\""; do
  grep -qF "${line%%=*}" ~/.bashrc || echo "$line" >> ~/.bashrc
done

echo "== 6b/8 playbooks + dev-workflow skill (machine-local, gitignored)"
cp tools/dev-workflow/AGENTS.md AGENTS.md
cp tools/dev-workflow/HACKATHON.md HACKATHON.md
mkdir -p .agents/skills/dev-workflow
cp tools/dev-workflow/skill/SKILL.md .agents/skills/dev-workflow/SKILL.md

echo "== 6c/8 ssh alias for deploy server"
touch "$HOME/.ssh/config"
grep -q 'docker-server-access' "$HOME/.ssh/config" || cat tools/dev-workflow/ssh-config >> "$HOME/.ssh/config"

echo "== 7/8 gbrain install + init"
command -v gbrain >/dev/null 2>&1 || bun install -g gbrain
gbrain config get database_path >/dev/null 2>&1 || gbrain init --pglite --path "$HOME/.gbrain/brain.pglite" --no-embedding --non-interactive --json
bash tools/hackathon-setup.sh

echo "== 8/8 python venv"
[ -d .venv ] || uv venv .venv
UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}" uv pip install --python .venv/bin/python -r requirements.txt

echo "== + bridge as systemd user service (autostart)"
if command -v systemctl >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/llm-bridge.service" <<EOF
[Unit]
Description=LiteLLM bridge (DBK team, port 4000)
After=network-online.target

[Service]
WorkingDirectory=$(pwd)
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$(pwd)/tools/llm-bridge.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now llm-bridge.service
  loginctl enable-linger "$USER" 2>/dev/null || true
else
  echo "  no systemd — run tools/llm-bridge.sh manually per session"
fi

echo
echo "Done. Verify: python3 tools/council.py --self-test"
