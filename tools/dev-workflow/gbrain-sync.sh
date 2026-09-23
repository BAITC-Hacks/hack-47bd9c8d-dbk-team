#!/usr/bin/env bash
# gbrain-sync.sh — PostToolUse hook (Bash/shell matcher): incremental gbrain
# sync after HEAD-advancing git ops. Replaces gsd-graphify-update.sh.
# Opt-in per repo: requires a .gbrain marker file at the repo root.
# Fail-open: always exits 0, never blocks the tool call.
set -uo pipefail

INPUT=$(cat 2>/dev/null || true)
[ -n "$INPUT" ] || exit 0

CMD=$(printf '%s' "$INPUT" | node -e '
let d = "";
process.stdin.on("data", c => d += c);
process.stdin.on("end", () => {
  try {
    const c = JSON.parse(d).tool_input?.command;
    process.stdout.write(Array.isArray(c) ? c.join(" ") : String(c || ""));
  } catch {}
});
' 2>/dev/null)

case "$CMD" in
  *"git commit"*|*"git merge"*|*"git pull"*|*"git rebase"*|*"git cherry-pick"*) ;;
  *) exit 0 ;;
esac

[ -z "${CI:-}" ] || exit 0
REPO=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -f "$REPO/.gbrain" ] || exit 0
command -v gbrain >/dev/null 2>&1 || exit 0

( gbrain sync --repo "$REPO" --strategy code --full && cd "$REPO" && gbrain compile-context --target codex --include tools/,decisions/ ) </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0
