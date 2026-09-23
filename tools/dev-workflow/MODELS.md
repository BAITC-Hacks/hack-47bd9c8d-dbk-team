# Подключение и переключение моделей — DBK team

Все корпоративные модели идут через LiteLLM-мост (порт 4000) на шлюз Baiterek.
Мост поднимается сетапом как systemd-сервис и стартует сам при логине.

## Доступные модели

| Модель | Контекст | Чем хороша | Как вызвать в codex |
|---|---|---|---|
| `glm-5.3-flash` | — | быстрый дефолт | `codex -p glm-flash` |
| `kimi-k3` | 1M | чтение больших репо, исследование | `codex -p kimi` |
| `deepseek-v4-1-flash` | 256K, vision | кодинг, картинки | `codex -p deepseek` |
| `glm-5.3` | — | полная GLM | только через API моста |
| `qwen3-8-27b-fp8` | — | запасная | только через API моста |

Без `-p` codex стартует на дефолтной модели (в день X — выданный OpenAI-ключ).

## Проверка, что мост жив

```bash
systemctl --user status llm-bridge
curl -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer $LITELLM_API_KEY"
journalctl --user -u llm-bridge -f   # логи, если что-то не так
```

Ручной перезапуск после правок `tools/litellm.yaml`: `systemctl --user restart llm-bridge`.
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
2. `systemctl --user restart llm-bridge`.
3. Для профиля codex: создать `~/.codex/<имя>.config.toml` по образцу kimi.config.toml.

## День X: выданный OpenAI-ключ

1. Вставить в `.env`: `OPENAI_API_KEY=sk-...`
2. Проверить: `python3 tools/agents_smoke.py` (каноничная обвязка Agents SDK).
3. Ядро продукта — только на нём (требование правил); корпоративные модели — наш
   внутренний инструментарий, в код продукта не идут.

## Если мост/Baiterek упал

Codex переключаем на выданный OpenAI-ключ (дефолтный профиль), разработка не встаёт.
Каунсил и gbrain-энричмент подождут — это инструментарий, не продукт.
