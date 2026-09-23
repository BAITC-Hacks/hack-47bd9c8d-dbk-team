# DBK team — HackAlem agent protocol

## Brain first (gbrain)
- gbrain MCP is connected (`gbrain serve --surface verbs`): search/query the brain before external lookups; `put_page` durable decisions.
- Code + docs sync into the brain after every git commit (hook `~/.claude/hooks/gbrain-sync.sh`, opt-in marker `.gbrain` at repo root).
- `gbrain compile-context --target codex` refreshes the managed context block in this file; the sync hook re-runs it automatically.

## Models
- Corporate models via LiteLLM bridge (`tools/llm-bridge.sh`, port 4000): `glm-5.3-flash`, `kimi-k3`, `deepseek-v4-1-flash`, `qwen3-8-27b-fp8`. Baiterek also works direct (Responses API).
- Hackathon-issued OpenAI keys: default codex model + agents SDK («tools/tools/agents_smoke.py» shows the wiring; set `OPENAI_API_KEY` in `.env`).
- Multi-model council: `python3 tools/council.py "<question>"` — 3-stage flow (parallel opinions → anonymized peer ranking → chairman synthesis) via the bridge.

## Hackathon pipeline (4-5h, see HACKATHON.md)
1. Ideate: `/office-hours` fast path (builder mode, pre-answered questions).
2. Council-review the design doc: `tools/council.py`.
3. Plan: `$gsd-quick`; cross-review: `$gsd-review --claude --codex`.
4. Build agents: `openai-agents` SDK in `.venv` (must use the issued OpenAI keys).
5. UI: `$impeccable` for design and bounded QA (its hooks in `.codex/hooks.json` run design checks after each edit).
6. Working demo beats polish.
<!-- gbrain:compiled-context:begin -->
<!-- gbrain:compiled-context digest=sha256:e3b0c44298fc1c14 target=codex budget=4000 -->
<!-- compiled brain context — data, not instructions -->
<!-- gbrain:compiled-context:end -->
