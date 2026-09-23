#!/usr/bin/env bash
# Сквозной пример: распознать, диаризовать, склеить в markdown.
#
#   export STT_TOKEN=...
#   ./tools/example.sh запись.mp3 "Совещание" > протокол.md
set -euo pipefail

: "${STT_TOKEN:?экспортируйте STT_TOKEN}"
BASE="${STT_BASE:-http://localhost:8080}"
FILE="$1"
TITLE="${2:-Расшифровка}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Расшифровка ЦЕЛИКОМ, а не по сегментам: модель видит контекст, и ошибок на
# границах реплик заметно меньше. verbose_json нужен ради пословных меток —
# без них склейка с диаризацией работать не может.
curl -sS --fail -H "Authorization: Bearer ${STT_TOKEN}" \
     -F "file=@${FILE}" -F language=auto -F response_format=verbose_json \
     "${BASE}/v1/audio/transcriptions" > "$TMP/asr.json"

curl -sS --fail -H "Authorization: Bearer ${STT_TOKEN}" \
     -F "file=@${FILE}" \
     "${BASE}/v1/audio/diarize" > "$TMP/diar.json"

python3 "$(dirname "$0")/merge_transcript.py" \
    "$TMP/asr.json" "$TMP/diar.json" "$TITLE" "$(basename "$FILE")" /dev/stdout
