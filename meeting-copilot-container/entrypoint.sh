#!/usr/bin/env bash
# Пайплайн: аудио (+vtt?) -> mp3 -> транскрибация (ai.kdb.kz) -> склейка -> summary.
#
# Если VTT целиком на английском (кириллица не встречается), аудио на
# распознавание не отправляется — текст берётся прямо из субтитров VTT,
# реплики схлопываются по говорящему, и сразу выполняется суммаризация.
#
# Если VTT не передан (видео/аудио без субтитров Zoom, например запись с
# телефона), спикеры определяются диаризацией ai.kdb.kz (/api/diar) — вместо
# имён будут безымянные "Speaker 0", "Speaker 1" и т.д.
#
# Использование:
#   entrypoint.sh <audio_file> [vtt_file] [output_dir]
#
# vtt_file распознаётся по расширению .transcript.vtt: если второй аргумент
# ему не соответствует, он считается output_dir, а VTT — отсутствующим.
#
# В output_dir (по умолчанию /artifacts/<имя_аудиофайла>) сохраняются только
# финальные артефакты:
#   transcript.json  - результат merge_transcript.py (vtt+json, только vtt, либо json+диаризация)
#   summary.md        - результат summarize_transcript.py
#   summary.pdf       - тот же summary в PDF (export_pdf.py); если экспорт
#                       не удался, файла просто не будет
#
# Промежуточные файлы (audio.mp3, ответы ai.kdb.kz) создаются во временной
# директории и удаляются по завершении — не сохраняются.

set -euo pipefail

usage() {
  echo "Использование: $0 <audio_file> [vtt_file] [output_dir]" >&2
  echo "  audio_file  - .mp3 / .m4a / .mp4 файл записи встречи" >&2
  echo "  vtt_file    - (опционально) *.transcript.vtt с таймингами/именами говорящих (Zoom)." >&2
  echo "                Если не передан — спикеры определяются диаризацией ai.kdb.kz." >&2
  echo "  output_dir  - куда сложить артефакты (по умолчанию /artifacts/<имя_аудио>)" >&2
  exit 1
}

# POST файла в ai.kdb.kz с проверкой HTTP-кода: call_ai_kdb <url> <out_file> [доп. curl -F ...]
call_ai_kdb() {
  local url="$1" out_file="$2"
  shift 2
  local http_code
  http_code=$(curl -s -o "$out_file" -w "%{http_code}" "$url" \
    -H "Authorization: Bearer ${AI_KDB_TOKEN}" "$@")
  if [ "$http_code" != "200" ]; then
    echo "[!] Ошибка запроса к $url, HTTP $http_code:" >&2
    cat "$out_file" >&2
    exit 1
  fi
}

[ $# -ge 1 ] || usage

AUDIO_FILE="$1"
ARG2="${2:-}"
ARG3="${3:-}"
BASENAME="$(basename "${AUDIO_FILE%.*}")"

if [[ -n "$ARG2" && "$ARG2" == *.transcript.vtt ]]; then
  VTT_FILE="$ARG2"
  OUTPUT_DIR="${ARG3:-/artifacts/$BASENAME}"
else
  VTT_FILE=""
  OUTPUT_DIR="${ARG2:-/artifacts/$BASENAME}"
fi

: "${AI_KDB_URL:=https://ai.kdb.kz}"
: "${DEFAULT_LANGUAGE:=ru}"

[ -f "$AUDIO_FILE" ] || { echo "[!] Аудиофайл не найден: $AUDIO_FILE" >&2; exit 1; }
if [ -n "$VTT_FILE" ]; then
  [ -f "$VTT_FILE" ] || { echo "[!] VTT файл не найден: $VTT_FILE" >&2; exit 1; }
fi

mkdir -p "$OUTPUT_DIR"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
MP3_FILE="$WORK_DIR/audio.mp3"
MERGED_JSON="$OUTPUT_DIR/transcript.json"

if [ -n "$VTT_FILE" ]; then
  echo "[*] Проверка языка VTT ($VTT_FILE)" >&2
  VTT_LANG="$(python3 merge_transcript.py --detect-lang "$VTT_FILE")"
else
  VTT_LANG=""
fi

if [ "$VTT_LANG" = "en" ]; then
  echo "[i] VTT целиком на английском — пропускаю распознавание речи, беру текст из VTT" >&2
  echo "[2/2] Склейка реплик VTT (без аудио) -> transcript.json" >&2
  python3 merge_transcript.py "$VTT_FILE" "$MERGED_JSON" --vtt-only
else
  if [ -z "${AI_KDB_TOKEN:-}" ]; then
    echo "[!] AI_KDB_TOKEN не задан. Передайте .env через --env-file / env_file." >&2
    exit 1
  fi

  echo "[1/4] Подготовка аудио -> mp3 ($AUDIO_FILE)" >&2
  if [[ "${AUDIO_FILE,,}" == *.mp3 ]]; then
    cp "$AUDIO_FILE" "$MP3_FILE"
  else
    ffmpeg -y -loglevel error -i "$AUDIO_FILE" -vn -ar 44100 -ac 2 -b:a 192k "$MP3_FILE"
  fi

  echo "[2/4] Транскрибация через ai.kdb.kz (язык: $DEFAULT_LANGUAGE)" >&2
  RAW_JSON="$WORK_DIR/transcript_raw.json"
  call_ai_kdb "${AI_KDB_URL%/}/api/whisper/v1/audio/transcriptions" "$RAW_JSON" \
    -F "file=@${MP3_FILE}" \
    -F "language=${DEFAULT_LANGUAGE}" \
    -F "response_format=verbose_json"

  if [ -n "$VTT_FILE" ]; then
    echo "[3/4] Склейка VTT + JSON -> transcript.json" >&2
    python3 merge_transcript.py "$VTT_FILE" "$RAW_JSON" "$MERGED_JSON"
  else
    echo "[3/4] VTT не передан — диаризация через ai.kdb.kz (/api/diar)" >&2
    DIAR_JSON="$WORK_DIR/diarization.json"
    call_ai_kdb "${AI_KDB_URL%/}/api/diar/v1/audio/diarize" "$DIAR_JSON" \
      -F "file=@${MP3_FILE}"

    echo "[3b/4] Склейка транскрипции + диаризации -> transcript.json" >&2
    python3 merge_transcript.py "$RAW_JSON" "$DIAR_JSON" "$MERGED_JSON" --diar-merge
  fi
fi

echo "[4/4] Суммаризация -> summary.md" >&2
SUMMARY_MD="$OUTPUT_DIR/summary.md"
python3 summarize_transcript.py "$MERGED_JSON" "$SUMMARY_MD"

# PDF — производный артефакт: если экспорт сорвался (нет шрифта с кириллицей,
# битая разметка), транскрипт и summary уже готовы и терять их из-за этого
# нельзя. Поэтому шаг неблокирующий, несмотря на set -e.
echo "[4b/4] Экспорт summary.md -> summary.pdf" >&2
SUMMARY_PDF="$OUTPUT_DIR/summary.pdf"
if ! python3 export_pdf.py "$SUMMARY_MD" "$SUMMARY_PDF"; then
  echo "[!] Не удалось собрать summary.pdf — пропускаю, summary.md на месте" >&2
  rm -f "$SUMMARY_PDF"
fi

echo "[+] Готово. Артефакты в $OUTPUT_DIR:" >&2
ls -la "$OUTPUT_DIR" >&2
