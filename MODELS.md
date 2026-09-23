# Подключение и переключение моделей — DBK team

Все корпоративные модели идут через LiteLLM-мост (порт 4000) на шлюз Baiterek.
Мост поднимается сетапом как сервис с автостартом при логине:
systemd user service на Linux, launchd user agent (`kz.dbk.llm-bridge`) на macOS.

## Доступные модели

| Модель | Контекст | Чем хороша | Как вызвать в codex |
|---|---|---|---|
| `glm-5.3-flash` | — | быстрый дефолт | `codex -p glm-flash` |
| `kimi-k3` | 1M | чтение больших репо, исследование | `codex -p kimi` |
| `deepseek-v4-1-flash` | 256K, vision | кодинг, картинки | `codex -p deepseek` |
| `glm-5.3` | 1M | полная GLM | `codex -p glm` |
| `qwen3-8-27b-fp8` | — | запасная | только через API моста |

Без `-p` codex стартует на дефолтной модели (в день X — выданный OpenAI-ключ).

## Проверка, что мост жив

```bash
curl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer $LITELLM_API_KEY"

# Linux (systemd):
systemctl --user status llm-bridge
journalctl --user -u llm-bridge -f        # логи

# macOS (launchd):
launchctl print "gui/$(id -u)/kz.dbk.llm-bridge" | head
tail -f /tmp/llm-bridge.err               # логи
```

Ручной перезапуск после правок `tools/litellm.yaml`:
`systemctl --user restart llm-bridge` (Linux) или
`launchctl kickstart -k "gui/$(id -u)/kz.dbk.llm-bridge"` (macOS).
Без systemd: `bash tools/llm-bridge.sh` в отдельном терминале.

## Вызов моделей напрямую из кода (OpenAI-совместимый API)

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:4000/v1", api_key=os.environ["LITELLM_API_KEY"])
client.chat.completions.create(model="deepseek-v4-1-flash", messages=[...])
```

Baiterek напрямую (без моста): base_url `https://llm.baiterek.gov.kz/v1`,
ключ `BAITEREK_LLM_GATEWAY_API_KEY` из `.env`.

## Каунсил моделей (второе мнение по архитектуре)

```bash
python3 tools/council.py "твой вопрос"     # kimi + deepseek + glm голосуют, deepseek председатель
python3 tools/council.py --self-test       # проверка, что всё живо
```

## Добавить новую модель на мост

1. В `tools/litellm.yaml` в `model_list` дописать блок по образцу существующих
   (model_name, model: openai/<имя-на-шлюзе>, api_base, api_key из env).
2. Перезапустить мост (см. команды выше).
3. Для профиля codex: создать `~/.codex/<имя>.config.toml` по образцу kimi.config.toml.

## День X: выданный OpenAI-ключ

1. Вставить в `.env`: `OPENAI_API_KEY=sk-...`
2. Проверить: `python3 agents_smoke.py` (каноничная обвязка Agents SDK).
3. Ядро продукта — только на нём (требование правил); корпоративные модели — наш
   внутренний инструментарий, в код продукта не идут.

## Если мост/Baiterek упал

Codex переключаем на выданный OpenAI-ключ (дефолтный профиль), разработка не встаёт.
Каунсил и gbrain-энричмент подождут — это инструментарий, не продукт.
