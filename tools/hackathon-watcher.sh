#!/usr/bin/env bash
# HackAlem day-X watcher: stage announcements + push/commit reminders.
# Start at 0:00 in a spare terminal:  bash tools/hackathon-watcher.sh
# Or retroactively:                   bash tools/hackathon-watcher.sh "10:00"
set -uo pipefail
cd "$(dirname "$0")/.."

if [ $# -ge 1 ]; then T0=$(date -d "$1" +%s); else T0=$(date +%s); fi

# minutes-from-T0 → stage message (fired once each)
STAGES=(
  "0|🚀 0:00 СТАРТ. Выбор кейса — 15 минут, нет консенсуса = решает лид"
  "15|🧠 0:15 office-hours fast path → дизайн-док → council-review (30 мин)"
  "45|⚠️ 0:45 hello world через весь пайплайн. ГЕЙТ 1: деплой на app.aibots.kz до 1:00"
  "60|🔨 1:00 must-скоуп: агентное ядро + UI параллельно. Шаблон уже в репо?"
  "180|🔗 3:00 интеграция end-to-end + первый прогон демо-сценария"
  "210|✨ 3:30 should-скоуп ТОЛЬКО если must зелёный. Иначе чиним must"
  "255|🧊 4:15 КОД-ФРИЗ (ГЕЙТ 2). README, слайды, репетиция демо х2"
  "270|📤 4:30 САБМИТ на платформе. Перед этим: git log по 3 машинам + прогон на ключи"
  "295|📤 4:55 повторный сабмит, если что-то допилили"
  "300|🏁 5:00 стоп. Демо: один сценарий, 3 минуты, говорит UI-человек"
)

say() {
  echo "[$(date +%H:%M:%S)] $*"
  command -v notify-send >/dev/null 2>&1 && notify-send -u critical "HackAlem" "$*" 2>/dev/null || true
  printf '\a'  # bell
}

declare -A FIRED=()
LAST_PUSH_REMINDER=-1

say "Watcher started. T0 = $(date -d "@$T0" +%H:%M). Жёсткие гейты: деплой 1:00, код-фриз 4:15."

while true; do
  NOW=$(date +%s)
  ELAPSED=$(( (NOW - T0) / 60 ))

  for entry in "${STAGES[@]}"; do
    M=${entry%%|*}; MSG=${entry#*|}
    if [ "$ELAPSED" -ge "$M" ] && [ -z "${FIRED[$M]:-}" ]; then
      FIRED[$M]=1; say "$MSG"
    fi
  done

  # push reminder every 20 min (starting at :20)
  if [ "$ELAPSED" -gt 0 ] && [ $((ELAPSED % 20)) -eq 0 ] && [ "$LAST_PUSH_REMINDER" -ne "$ELAPSED" ]; then
    LAST_PUSH_REMINDER=$ELAPSED
    say "⏱ push-пауза: pull --rebase → push. Ветки worktree — rebase main + мерж."
  fi

  # hourly personal-commit check (at :00 of each hour)
  if [ "$ELAPSED" -gt 0 ] && [ $((ELAPSED % 60)) -eq 0 ] && [ -z "${FIRED[commit-$ELAPSED]:-}" ]; then
    FIRED[commit-$ELAPSED]=1
    AUTHORS=$(git log --since="1 hour ago" --format='%an' 2>/dev/null | sort -u | tr '\n' ' ')
    say "📝 Час прошёл — каждый коммитит! За последний час: ${AUTHORS:-никого — СТОП, все коммитим}. Должно быть 3 имени."
  fi

  [ "$ELAPSED" -ge 305 ] && { say "Watcher done. Удачи на демо!"; break; }
  sleep 30
done
