#!/usr/bin/env python3
"""Anti-god-file PostToolUse hook (Codex + Claude payloads).
Warns (non-blocking) when an edited source file exceeds 400 lines.
Reads hook JSON from stdin; emits additionalContext JSON only on violation."""
import sys, json, os, re

LIMIT = 400
EXTS = (".py", ".ts", ".tsx", ".js", ".jsx")

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

ti = data.get("tool_input") or {}
paths = set()
if ti.get("file_path"):
    paths.add(ti["file_path"])
cmd = ti.get("command") or ""
if isinstance(cmd, list):
    cmd = " ".join(map(str, cmd))
paths.update(re.findall(r"\*\*\* (?:Update|Add) File: (\S+)", cmd))

big = []
for p in paths:
    if not p.endswith(EXTS) or not os.path.isfile(p):
        continue
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            n = sum(1 for _ in f)
    except Exception:
        continue
    if n > LIMIT:
        big.append(f"{p} ({n} lines)")

if big:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"⚠ ANTI-GOD-FILE: {', '.join(big)} exceeds {LIMIT} lines. "
                "Split by responsibility; do not pile more into this file."
            ),
        }
    }))

sys.exit(0)
