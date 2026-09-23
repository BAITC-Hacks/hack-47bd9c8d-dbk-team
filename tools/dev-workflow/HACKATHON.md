# HackAlem playbook — DBK team (4-5h)

One-time setup (normal shell, not sandbox): `bash tools/hackathon-setup.sh`
At venue: `set -a; . .env; set +a`, add issued `OPENAI_API_KEY` to `.env`, `tools/llm-bridge.sh &`.

## Timeline

| Time | Block | Tooling |
|------|-------|---------|
| 0:00-0:40 | Ideation | `/office-hours` fast path (below) |
| 0:40-1:00 | Design-doc council review | `tools/council.py "Review this design doc: ..."` |
| 1:00-1:20 | Plan + cross-review | `$gsd-quick`, `$gsd-review --claude --codex` |
| 1:20-3:30 | Build agents | `openai-agents` SDK + issued OpenAI keys |
| 3:00-4:00 | UI (parallel track) | `$impeccable` |
| 4:00-4:30 | Deploy + demo rehearsal | `tools/deploy.sh` → app.aibots.kz; council: "poke holes in this demo narrative" |
| 4:30-5:00 | README + submission | organizers' README prompt (below) → «Сдать решение» on the platform |

## Venue rules (from organizers' docs — affects how we work)

- **Every member must contribute personally** — everyone commits from their own
  machine (set `git config user.name/email` per machine; `$dev-workflow` does the rest).
- Breaks: 60 min total per person; **last hour — no leaving the zone**.
- **No personal hotspots / tethering** — each machine is autonomous: local bridge,
  local gbrain. Nothing shared over LAN.
- No API keys in GitHub (`.env` is gitignored; check `git status` before pushing).
- Submission: platform → your case → «Сдать решение»; updateable until deadline.

## Final README (organizers' template)

Their exact prompt is in `docs/Инструкция_для_участников_HackAlem_AI.txt` (section
"Промпт для README") — paste it into Codex at 4:30. Required sections: название,
проблема, что реализовано, сценарий, технологии, архитектура, установка/запуск,
как проверить, данные/интеграции, ограничения, **ссылка на deployed-версию** —
use `https://app.aibots.kz`. Only verifiable facts from the repo, no inventions.

## 1. Office-hours fast path

Open with a fully-formed brief — the skill then skips Phase 2 questioning and
goes straight to Premise Challenge + Alternatives:

> /office-hours — hackathon, 4h build window, team of N. Idea: <2-3 sentences>.
> Target demo: <what judges see working>. Constraints: must use OpenAI API keys
> issued at venue; corporate models available via our bridge. Treat this as a
> fully formed plan: skip questioning, run Premise Challenge + Alternatives,
> builder mode, skip landscape search and second opinion.

Skip when offered: landscape search (2.75), Claude second opinion (3.5 — the
council replaces it), visual mockups ($impeccable handles UI later), YC resources
(Phase 6). Keep: Premise Challenge, Alternatives, design doc.

## 2. Council review (replaces Phase 3.5 second opinion)

```bash
tools/llm-bridge.sh &   # once per session
python3 tools/council.py "You are hackathon judges. Attack this design doc: $(cat docs/designs/<file>.md)"
```

Models: `kimi-k3`, `deepseek-v4-1-flash`, `glm-5.3-flash` (env `COUNCIL_MODELS`).
Chairman: `deepseek-v4-1-flash` (env `COUNCIL_CHAIRMAN`). Add `claude-opus-5` /
`gpt-5` by uncommenting them in `tools/litellm.yaml` when keys exist.

## 3. GSD review lanes

`$gsd-review --claude --codex` — claude CLI (Opus lane) + codex (OpenAI lane).
Corporate-model lanes go through the council instead of gsd reviewer instances:
codex's reviewer adapter binds `--model` to the default provider, which can't
reach the bridge per-instance. If a per-instance config is wanted later:
`review.reviewer_instances.<name>.{cli,model}` in `.planning/config.json`.

`$gsd-review-backlog` — unchanged; run only if backlog items accumulate.

## 4. Build

- `.venv` has `openai-agents`; «tools/tools/agents_smoke.py» is the canonical gateway wiring
  (swap `base_url`/key for the issued OpenAI key, or keep Baiterek for non-OpenAI calls).
- AI Elements (React/shadcn chat components) if the demo needs a web UI — see README Toolbox.
- `template/` — готовый Next.js + AI Elements чат со stub-агентом (`app/api/chat/route.ts`,
  реальный SSE-стрим без ключа; в день X меняем заглушку на OpenAI Agents SDK).
  Деплой проверен репетицией: `tools/deploy.sh` → https://app.aibots.kz (порт 8181, compose в корне).
  ПРАВИЛО ОРГАНИЗАТОРОВ: в репо только инфраструктура, кода нет → template лежит ВНЕ репо:
  у лида `~/dbk-assets/template`, у тиммейтов `template.tar.gz` в пакете.
  День X, 0:00: `tar -xzf template.tar.gz` в корень репо → `git add template && git commit` — и погнали.

## 5. UI protocol (impeccable)

`$impeccable` runs the whole UI track: design direction, execution, and design QA
via its hooks (already wired in `.codex/hooks.json` — they fire after each edit).
One bounded QA pass, not open-ended polishing.

## 6. gbrain as project memory

- Every commit auto-syncs code+docs into the brain (hook), then recompiles the
  AGENTS.md context block — every new session starts with current project knowledge.
- Embeddings: `qwen3-embedding-4b` via Baiterek (semantic search); chat/expansion:
  `deepseek-v4-1-flash`. Configured by `tools/hackathon-setup.sh`.
- Note: gbrain skips `README.md` on import — put durable notes in `docs/` or
  `gbrain capture`.

## Решения дня X (закрыто грилем, не переоткрывать)

**Кейс и скоуп**
- Выбор кейса: максимум демо-эффекта при минимуме бэкенда + естественное место для
  OpenAI Agents SDK. 15 минут, нет консенсуса — решает тимлид.
- Must: один агентский сценарий end-to-end на выданных OpenAI-ключах + живой UI на
  app.aibots.kz + README по шаблону организаторов.
- Should: council/мультимодельность как фича продукта.
- Never: вторая LLM-фича, чат-память, авторизация, ручная добыча данных (>20 мин — мокаем).

**Роли (фиксированы с первой минуты)**
- Лид: архитектура + агентное ядро (OpenAI SDK).
- Второй: UI-трек целиком ($impeccable), он же говорящий на демо.
- Третий: данные/тулы агентов + деплой + README с 0:30 + чек-лист сабмита с 3:30.

**OpenAI vs Baiterek**
- Ядро продукта — строго OpenAI Agents SDK на выданных ключах (требование правил).
- Baiterek/council — только внутренний инструментарий, в код продукта не лезет.

**Git**
- Транк, пуш каждые 20 минут по таймеру, `pull --rebase` перед пушем.
- Каждый в своих файлах (роли это почти гарантируют). Конфликт = стоп, резолвит лид сразу.
- КАЖДЫЙ участник коммитит со своей машины МИНИМУМ раз в час (требование организаторов —
  личные коммиты). Пустых коммитов нет: нечего коммитить = ты застрял, эскалация лиду.
  Лид каждый час сверяет `git log --since=1h --format='%an' | sort -u` — должно быть три имени.
- В 0:00 каждый запускает у себя `bash tools/hackathon-watcher.sh` — объявляет этапы
  (оба гейта), напоминает о пушах каждые 20 мин и о почасовых коммитах с выводом авторов.

**Ветки и распределение задач (branch-per-person)**
- Лид — ветка `agent-core`: агентное ядро на OpenAI Agents SDK, промпты, тулчейн,
  `template/app/api/**` (замена stub на реального агента), `package.json` (новые зависимости
  объявляет в чат СРАЗУ).
- Второй — ветка `ui`: `template/app/page.tsx`, `template/components/**`, `template/public/**`,
  UX демо-сценария, дизайн через $impeccable, слайды для жюри.
- Третий — ветка `data-tools`: данные кейса (моки/firecrawl), функции-тулы агента,
  `docker-compose.yml`/деплой, README по шаблону организаторов (с 0:30), чек-лист сабмита.
- Контракт между ветками фиксируется в 0:15 в дизайн-доке: SSE-протокол `/api/chat`
  (уже задан шаблоном) + сигнатуры тулов агента. Контрактные файлы правит только владелец.
- МЕРДЖ: не «потом», а каждые 30-40 минут в main (rebase + merge, лид резолвит).
  Полный мердж всех веток в 3:00 — к интеграции всё уже в main. В 4:15 мерджей НЕТ.

**Параллельные Codex-окна (git worktree)**
- Окно = `git worktree add ../hack-<task> -b feature-<task>`; `.env` скопировать,
  `.venv` symlink'нуть (не в гите). Окна в одной папке на разных ветках ЗАПРЕЩЕНЫ.
- Ветки короткие: `git rebase main` + мерж в main каждые 30-40 минут, лид резолвит.
- `.planning/`, `HACKATHON.md` правит только main-окно.
- gbrain общий (один на машину, MCP для всех окон). Маркер `.gbrain` не в гите →
  worktree-окна не синкают: мозг наполняется только из main после мержей, без мусора
  из незмердженных веток. Координация: все окна читают мозг (`gbrain query` / MCP),
  решения — `gbrain put`; сами изменения управляются git-мержами, не мозгом.

**Тайминг (два жёстких гейта, остальное плавает)**
- 0:00–0:15 выбор кейса → 0:15–0:45 office-hours fast path + council-review →
  0:45–1:00 hello world через весь пайплайн (ГЕЙТ 1) → 1:00–3:00 must-скоуп →
  3:00–3:30 интеграция + прогон демо → 3:30–4:15 should только если must зелёный →
  4:15 КОД-ФРИЗ (ГЕЙТ 2): README, репетиция, сабмит.
- Деплой `tools/deploy.sh` каждый час, последний в 3:45.

**Фолбэки**
- Мост/Baiterek упал → codex на выданный OpenAI-ключ напрямую, разработка не встаёт.
- OpenAI rate limit → кэш ответов в демо-сценарии, запасной ключ второго участника.
- Туннель/сервер лёг → демо с localhost:8181 на ноутбуке, тот же сценарий.

**Демо и сабмит**
- Один счастливый сценарий, ~3 минуты, говорит UI-человек, лид на клавиатуре страхует.
  Репетиция дважды в 4:15–4:45, включая «что говорим, пока агент думает».
- Сабмит в 4:30, повторный в 4:55. Перед первым: `git log --author` (коммиты с трёх
  машин) + прогон по репо на предмет ключей.
- README строго по требованиям организаторов (11 разделов, docs/Инструкция...txt п.7):
  что делает / что реализовано / технологии+архитектура / установка и запуск /
  ПРИМЕРЫ ЗАПРОСОВ для жюри (дословно) / данные и внешние сервисы / ограничения /
  ссылка https://app.aibots.kz. Шаблон: `tools/dev-workflow/README-TEMPLATE.md`
  (там же промпт организаторов для генерации черновика). Ничего не выдумывать.
