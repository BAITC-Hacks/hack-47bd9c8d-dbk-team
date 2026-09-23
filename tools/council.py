#!/usr/bin/env python3
"""LLM council (karpathy/llm-council flow, terminal-only) against the LiteLLM bridge.

Stage 1: every model answers in parallel.
Stage 2: every model ranks the anonymized answers; rankings are aggregated.
Stage 3: the chairman synthesizes the final answer from answers + rankings.

Usage:
  tools/llm-bridge.sh &                       # bridge on :4000 (once per session)
  tools/council.py "your hardest question"
  tools/council.py --self-test                # check bridge + models

Env overrides: COUNCIL_BASE_URL, COUNCIL_API_KEY, COUNCIL_MODELS (csv),
COUNCIL_CHAIRMAN.
"""
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.environ.get("COUNCIL_BASE_URL") or os.environ.get("BRIDGE_BASE") or "http://localhost:4000/v1"
KEY = os.environ.get("COUNCIL_API_KEY") or os.environ.get("LITELLM_API_KEY") or "sk-bridge"
# Cloudflare bot check 403s python-urllib — needed when BASE goes via llm.aibots.kz
UA = {"User-Agent": "curl/8.0"}
MODELS = os.environ.get("COUNCIL_MODELS", "kimi-k3,deepseek-v4-1-flash,qwen3-8-27b-fp8,claude-opus").split(",")  # glm-flash out while its relay is down
CHAIRMAN = os.environ.get("COUNCIL_CHAIRMAN", "deepseek-v4-1-flash")
CLAUDE_MODEL = os.environ.get("COUNCIL_CLAUDE_MODEL", "opus")


def chat(model, messages, timeout=180):
    if model == "claude-opus":  # no API key — headless Claude Code CLI (subscription auth)
        prompt = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        out = subprocess.run(["claude", "-p", prompt, "--model", CLAUDE_MODEL],
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip()
    req = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=json.dumps({"model": model, "messages": messages}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", **UA},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)["choices"][0]["message"]["content"]


def safe_chat(model, messages):
    try:
        return chat(model, messages)
    except Exception as exc:
        print(f"[warn] {model} failed: {exc}", file=sys.stderr)
        return None


def council(question):
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        opinions = list(pool.map(lambda m: safe_chat(m, [{"role": "user", "content": question}]), MODELS))
    answers = {m: o for m, o in zip(MODELS, opinions) if o}
    if not answers:
        sys.exit("council: no model answered — is the bridge up? (tools/llm-bridge.sh)")

    labels = {m: chr(ord("A") + i) for i, m in enumerate(answers)}
    anon = "\n\n".join(f"Response {labels[m]}:\n{o}" for m, o in answers.items())
    rank_prompt = (
        f"Question: {question}\n\n{anon}\n\n"
        "Rank these responses best to worst. Reply with ONLY the letters in order, e.g. B,A,C."
    )
    with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
        votes = list(pool.map(lambda m: safe_chat(m, [{"role": "user", "content": rank_prompt}]), MODELS))
    scores = {label: 0 for label in labels.values()}
    for vote in votes:
        if not vote:
            continue
        order = [c for c in vote.upper() if c in scores]
        for rank, label in enumerate(order):
            scores[label] += len(scores) - rank
    board = sorted(scores, key=scores.get, reverse=True)
    inv = {v: k for k, v in labels.items()}

    chair_prompt = (
        f"Question: {question}\n\nCouncil answers:\n{anon}\n\n"
        f"Peer ranking (best first): {', '.join(board)}\n\n"
        "You are the chairman. Synthesize the best final answer: resolve disagreements, "
        "keep what the top-ranked answers agree on, be direct and specific."
    )
    final = safe_chat(CHAIRMAN, [{"role": "user", "content": chair_prompt}])

    print("== Ranking ==")
    for label in board:
        print(f"  {label} ({inv[label]}): {scores[label]}")
    print("\n== Chairman (%s) ==\n%s" % (CHAIRMAN, final or "chairman failed — read ranking above"))
    print("\n== Individual answers ==")
    for m, o in answers.items():
        print(f"\n--- {labels[m]} = {m} ---\n{o}")


def self_test():
    req = urllib.request.Request(f"{BASE}/models", headers={"Authorization": f"Bearer {KEY}", **UA})
    with urllib.request.urlopen(req, timeout=15) as res:
        available = {m["id"] for m in json.load(res)["data"]}
    missing = [m for m in [CHAIRMAN, *MODELS] if m != "claude-opus" and m not in available]
    assert not missing, f"models not served by bridge: {missing}"
    reply = chat(MODELS[0], [{"role": "user", "content": "reply with: ok"}], timeout=60)
    assert reply.strip(), "empty reply"
    print(f"self-test ok: {len(available)} models, council={MODELS}, chairman={CHAIRMAN}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif len(sys.argv) > 1:
        council(" ".join(a for a in sys.argv[1:] if not a.startswith("--")))
    else:
        print(__doc__)
