#!/usr/bin/env bash
# Пайплайн: аудио (+vtt?) -> mp3 -> транскрибация (ai.kdb.kz) -> склейка -> summary.
#
# Если VTT целиком на английском (кириллица не встречается), аудио на
# распознавание не отправляется — текст берётся прямо из субтитров VTT,
# реплики схлопываются по говорящему, и сразу выполняется суммаризация.
#
# Если VTT не передан (видео/аудио без субтитров Zoom, например запись с
# телефона), спикеры определяются диаризацией — вместо имён будут безымянные
# "Speaker 0", "Speaker 1" и т.д. Модель диаризации различает ровно четыре
# голоса: пятый участник сливается с одним из четырёх.
#
# Речевая служба выбирается переменной DEFAULT_PROVIDER:
#   speech_stack (по умолчанию) - свой стек, stt.aibots.kz, токен STT_TOKEN;
#   kdb                         - ai.kdb.kz, токен AI_KDB_TOKEN.
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
# Промежуточные файлы (audio.mp3, ответы речевой службы) создаются во временной
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

# POST файла в речевую службу с проверкой HTTP-кода:
#   call_speech_api <url> <out_file> [доп. curl -F ...]
# User-Agent задаётся явно: шлюз speech_stack стоит за Cloudflare, который
# отдаёт 403 на User-Agent по умолчанию у некоторых клиентов.
call_speech_api() {
  local url="$1" out_file="$2"
  shift 2
  local http_code
  http_code=$(curl -s -o "$out_file" -w "%{http_code}" "$url" \
    -H "Authorization: Bearer ${SPEECH_TOKEN}" \
    -H "User-Agent: dbk-meeting-copilot/1.0" "$@")
  if [ "$http_code" = "401" ]; then
    echo "[!] $url вернул 401." >&2
    echo "    Проверьте токен — и заодно путь: шлюз speech_stack закрывает 401" >&2
    echo "    и неизвестные пути, чтобы снаружи не был виден состав ручек." >&2
    cat "$out_file" >&2
    exit 1
  fi
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

: "${DEFAULT_LANGUAGE:=ru}"
: "${DEFAULT_PROVIDER:=speech_stack}"

# Провайдер распознавания и диаризации. Стеки различаются путями ручек и
# именем переменной с токеном, поэтому и то и другое выбирается здесь, а ниже
# по скрипту используются уже готовые TRANSCRIBE_URL / DIARIZE_URL.
case "${DEFAULT_PROVIDER}" in
  speech_stack|speech-stack|stt|aibots)
    # Имена переменных исторически разошлись: документация стека говорит
    # SPEECH_STACK_URL/STT_TOKEN, рабочий .env команды — STT_BASE_URL/
    # STT_API_KEY. Принимаем оба, как и config.py.
    SPEECH_BASE="${SPEECH_STACK_URL:-${STT_BASE_URL:-https://stt.aibots.kz}}"
    SPEECH_BASE="${SPEECH_BASE%/}"
    SPEECH_TOKEN="${STT_TOKEN:-${STT_API_KEY:-}}"
    SPEECH_TOKEN_VAR="STT_TOKEN (или STT_API_KEY)"
    TRANSCRIBE_URL="${SPEECH_BASE}/v1/audio/transcriptions"
    DIARIZE_URL="${SPEECH_BASE}/v1/audio/diarize"
    # Свой стек принимает ru | kk | en | auto; если язык задан отдельно для
    # него — он и побеждает, иначе берётся общий DEFAULT_LANGUAGE.
    LANGUAGE="${SPEECH_STACK_LANGUAGE:-$DEFAULT_LANGUAGE}"
    ;;
  kdb|kdb_whisper)
    : "${AI_KDB_URL:=https://ai.kdb.kz}"
    SPEECH_BASE="${AI_KDB_URL%/}"
    SPEECH_TOKEN="${AI_KDB_TOKEN:-}"
    SPEECH_TOKEN_VAR="AI_KDB_TOKEN"
    TRANSCRIBE_URL="${SPEECH_BASE}/api/whisper/v1/audio/transcriptions"
    DIARIZE_URL="${SPEECH_BASE}/api/diar/v1/audio/diarize"
    LANGUAGE="${DEFAULT_LANGUAGE}"
    ;;
  *)
    echo "[!] Неизвестный DEFAULT_PROVIDER='${DEFAULT_PROVIDER}'." >&2
    echo "    Допустимые значения: speech_stack, kdb." >&2
    exit 1
    ;;
esac

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
  if [ -z "${SPEECH_TOKEN}" ]; then
    echo "[!] ${SPEECH_TOKEN_VAR} не задан (провайдер ${DEFAULT_PROVIDER})." >&2
    echo "    Передайте .env через --env-file / env_file." >&2
    exit 1
  fi

  echo "[1/4] Подготовка аудио -> mp3 ($AUDIO_FILE)" >&2
  if [[ "${AUDIO_FILE,,}" == *.mp3 ]]; then
    cp "$AUDIO_FILE" "$MP3_FILE"
  else
    ffmpeg -y -loglevel error -i "$AUDIO_FILE" -vn -ar 44100 -ac 2 -b:a 192k "$MP3_FILE"
  fi

  echo "[2/4] Транскрибация через ${SPEECH_BASE} (язык: $LANGUAGE)" >&2
  RAW_JSON="$WORK_DIR/transcript_raw.json"
  # Запись распознаётся ЦЕЛИКОМ, а не по сегментам: модель видит контекст, и
  # ошибок на границах реплик заметно меньше. verbose_json обязателен — без
  # пословных меток времени склейка с диаризацией невозможна.
  # Поле prompt намеренно не передаётся: на материале speech_stack оно резко
  # портит результат.
  # Длинная запись режется на куски и склеивается обратно: шлюз за Cloudflare
  # не ждёт ответ дольше полутора минут и отдаёт 524, не дожидаясь. Короткая
  # уходит одним запросом, как раньше, — chunked_transcribe.py решает сам.
  python3 chunked_transcribe.py "$MP3_FILE" "$RAW_JSON" \
    --url "$TRANSCRIBE_URL" \
    --token "$SPEECH_TOKEN" \
    --language "$LANGUAGE" \
    --hotwords "${SPEECH_STACK_HOTWORDS:-}"

  if [ -n "$VTT_FILE" ]; then
    echo "[3/4] Склейка VTT + JSON -> transcript.json" >&2
    python3 merge_transcript.py "$VTT_FILE" "$RAW_JSON" "$MERGED_JSON"
  else
    echo "[3/4] VTT не передан — диаризация через ${DIARIZE_URL}" >&2
    DIAR_JSON="$WORK_DIR/diarization.json"
    call_speech_api "$DIARIZE_URL" "$DIAR_JSON" \
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
