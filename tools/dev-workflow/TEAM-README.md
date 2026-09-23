# hack-47bd9c8d-dbk-team
Hackathon team repository for DBK team

**Hackathon day: read `HACKATHON.md` (playbook), run `bash tools/hackathon-setup.sh` once in a normal shell. Agent protocol auto-loads from `AGENTS.md`.**

**Teammates (bare machine):** clone → `cp .env.example .env` + fill keys → `bash tools/dev-workflow-setup.sh`. Deploys the whole stack: bridge service, gbrain, profiles, MCP (gbrain/firecrawl/21st), skills, hooks, playbooks (AGENTS.md/HACKATHON.md). After that `$dev-workflow` skill is available in Codex for re-runs.

## Team git + deploy

- **One remote**: this repo (private, BAITC-Hacks org). 3 machines → clone, work on `main`, `git pull --rebase` before push, small frequent commits (the gbrain sync hook fires on each).
- **Demo server**: `docker-server` (SSH via Cloudflare Access — alias in `tools/dev-workflow/ssh-config`, lead adds your pubkey).
- **Deploy**: `tools/deploy.sh` → pulls on the server into `~/dbk` and `docker compose up -d --build` when a compose file exists. App must listen on **127.0.0.1:8181**.
- **Public URL**: `https://app.aibots.kz` → Cloudflare Tunnel `dbk-hack` → `docker-server:8181`. Ports 8000/8080/8088/8090/9000/9090 on the server are taken by other services — stay on 8181.

## Codex CLI → corporate models

Codex speaks only the Responses API. GLM gateway is Chat-Completions-only, so a local LiteLLM bridge sits in between; Baiterek gateway supports Responses natively and is used directly.

```bash
set -a; . .env; set +a              # keys for codex (Baiterek provider uses env_key)
tools/llm-bridge.sh                 # terminal 1, only for GLM (port 4000)
codex -p glm-flash                  # GLM-5.3-Flash via bridge
codex -p deepseek                   # deepseek-v4-1-flash, direct
codex -p kimi                       # kimi-k3, direct
```

Profiles live in `~/.codex/<name>.config.toml`, provider `bridge` in `~/.codex/config.toml`. Model ids for the bridge: `tools/litellm.yaml`. Other Baiterek models: `qwen3-8-27b-fp8`, `whisper-large-v3`, embeddings `bge-m3` / `qwen3-embedding-4b` / `qwen3-vl-embedding-8b`.

## Toolbox

- **Backend agents**: `openai-agents` Python SDK in `.venv` (see `tools/agents_smoke.py` for the gateway wiring).
- **Frontend (if web UI)**: [Vercel AI Elements](https://vercel.com/changelog/introducing-ai-elements) — open-source React components for AI apps (message threads, prompt input, reasoning panels), built on shadcn/ui + AI SDK `useChat`. Docs: https://ai-sdk.dev/elements. Pairs with a Next.js frontend talking to our Baiterek models.
