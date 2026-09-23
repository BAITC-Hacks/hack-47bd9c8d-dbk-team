---
name: dev-workflow
description: Deploy the full DBK team stack on a bare machine with Codex CLI — LiteLLM bridge (systemd service), gbrain memory (MCP + sync hooks + compiled context), codex profiles for corporate models (glm-flash/deepseek/kimi), MCP servers (gbrain, firecrawl, 21st.dev), GSD + gstack + impeccable skills, Python venv with openai-agents. Use when the user says "$dev-workflow", asks to set up the team environment, onboard a teammate, or restore the stack on a fresh machine.
---

# DBK dev-workflow bootstrap

One command deploys everything. The script is idempotent — safe to re-run.

## Step 1: Prereqs

Need: `codex`, `git`, `uv`, `node`/`npm`, `bun`. If missing, tell the user:
bun: `curl -fsSL https://bun.sh/install | bash` · uv: `curl -fsSL https://astral.sh/uv/install.sh | bash`

## Step 2: .env

The script stops if `.env` is missing or keys are empty — teammate copies
`.env.example` → `.env` and fills keys (get them from the team lead; never
commit `.env`).

## Step 3: Run the bootstrap

```bash
bash tools/dev-workflow-setup.sh
```

It needs write access to `$HOME` (codex config, `~/.gbrain`, `~/.claude`,
systemd user units) — run it in a normal terminal if the sandbox blocks it,
then come back.

What it installs:
- **Skills**: gsd-core (global), gstack (`/office-hours` etc.), impeccable (design QA hooks).
- **Codex profiles** (`~/.codex/*.config.toml`): `glm-flash`, `deepseek`, `kimi` + `coder`/`explorer` agents.
- **Codex config**: `bridge` + `baiterek` providers; MCP servers `gbrain`, `firecrawl`, `21st`.
- **Hooks**: `.codex/hooks.json` (repo — impeccable design QA + gbrain sync) and
  `~/.claude/hooks/gbrain-sync.sh` (brain sync after commits, auto `compile-context`).
- **gbrain**: PGLite brain, embeddings `qwen3-embedding-4b`, chat/expansion
  `deepseek-v4-1-flash` via Baiterek, provider keys in `~/.gbrain/.env`.
- **Bridge**: systemd user service `llm-bridge` (port 4000, autostart at boot).
- **Python**: `.venv` with `openai-agents`.

## Step 4: Verify (run all three)

```bash
python3 tools/council.py --self-test   # bridge + council models
gbrain query test                       # expect "clean miss", no degradation
systemctl --user status llm-bridge      # active (running), enabled
```

All green → report DONE with the model list. Any red → check
`journalctl --user -u llm-bridge` and `gbrain doctor --fast`, fix, re-run.

## Daily use after setup

- Models: `codex -p glm-flash|deepseek|kimi`; council: `python3 tools/council.py "<q>"`.
- Pipeline: `HACKATHON.md`; agent protocol auto-loads from `AGENTS.md`.
