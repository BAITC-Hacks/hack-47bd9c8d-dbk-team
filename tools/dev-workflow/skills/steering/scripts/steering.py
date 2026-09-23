#!/usr/bin/env python3
"""Generate and maintain Kiro-style steering documents."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Iterable

ROOT = Path(__file__).resolve().parents[5]
STEERING = ROOT / ".kiro" / "steering"
GENERATED_AT = "Generated from repository contents; verify before committing."


@dataclass
class Domain:
    name: str
    description: str
    paths: list[str]
    topics: list[str]


def command_output(command: list[str]) -> str | None:
    try:
        return subprocess.check_output(command, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def tracked_files() -> list[str]:
    output = command_output(["git", "ls-files"])
    if output:
        return output.splitlines()
    return [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def first_match(files: Iterable[str], pattern: str) -> str | None:
    regex = re.compile(pattern)
    for name in sorted(files):
        if regex.search(name):
            return name
    return None


def product_document(files: list[str]) -> str:
    readme = first_match(files, r"(^|/)README[^/]*$")
    return dedent(
        f"""
        # Product Steering

        **Status:** draft — fill in missing project facts before relying on this file.

        ## Mission

        Not yet defined.

        ## Users

        Not yet defined.

        ## Primary Jobs

        Not yet defined.

        ## Demo Outcome

        Not yet defined.

        ## Non-Goals

        - Do not add unrequested product scope.
        - Do not sacrifice a working demo for speculative architecture.

        ## Source Hints

        - Repository README: {readme or "not found"}

        {GENERATED_AT}
        """
    ).strip() + "\n"


def technology_document() -> str:
    package = read_json(ROOT / "package.json")
    python_deps: list[str] = []
    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        python_deps = [line.strip() for line in requirements.read_text().splitlines() if line.strip() and not line.startswith("#")]

    package_manager = "npm" if (ROOT / "package-lock.json").exists() else "bun" if (ROOT / "bun.lockb").exists() else "npm" if package else None
    languages = Counter()
    for path in tracked_files():
        if path.endswith((".py",)):
            languages["Python"] += 1
        elif path.endswith((".ts", ".tsx")):
            languages["TypeScript"] += 1
        elif path.endswith((".js", ".jsx")):
            languages["JavaScript"] += 1

    frameworks = []
    if package.get("dependencies", {}).get("next") or package.get("devDependencies", {}).get("next"):
        frameworks.append("Next.js")
    if any("fastapi" in dep.lower() for dep in python_deps):
        frameworks.append("FastAPI")
    if any("openai-agents" in dep.lower() for dep in python_deps):
        frameworks.append("OpenAI Agents SDK")

    return dedent(
        f"""
        # Technology Steering

        ## Stack

        - Languages: {", ".join(f"{name} ({count} tracked files)" for name, count in languages.most_common(4)) or "Not detected"}
        - Frameworks: {", ".join(frameworks) or "Not detected"}
        - Python dependencies: `requirements.txt` ({len(python_deps)} entries)
        - Node package metadata: `package.json` {f"({package.get('name', 'unnamed')})" if package else "not found"}
        - Package manager: {package_manager or "Not detected"}

        ## Environment

        - Python environment: `.venv`
        - Local secrets: `.env` (never commit)

        ## Commands

        Only add commands after verifying them in this repository.

        - Not yet defined.

        ## Constraints

        - Follow existing dependency manifests rather than installing ad-hoc packages.
        - Keep credentials in `.env`; never print or commit them.

        {GENERATED_AT}
        """
    ).strip() + "\n"


def structure_document(files: list[str]) -> str:
    top_dirs = sorted({path.split("/", 1)[0] for path in files if "/" in path and not path.split("/", 1)[0].startswith(".")})
    root_files = sorted({path for path in files if "/" not in path})
    top_dir_lines = "\n".join(f"- `{name}/`" for name in top_dirs) or "- No tracked directories found."
    root_file_lines = "\n".join(f"- `{name}`" for name in root_files[:20] if name != "README.md") or "- None"
    return dedent(
        f"""
        # Structure Steering

        ## Top-Level Layout

        {top_dir_lines}

        ## Root Files

        {root_file_lines}

        ## Where Changes Go

        - Not yet defined.

        ## Conventions

        - Prefer the nearest existing pattern before creating a new directory.
        - Update this file when directory responsibilities change.

        {GENERATED_AT}
        """
    ).strip() + "\n"


def domain_frontmatter(domain: Domain) -> str:
    lines = [
        "---",
        f"description: {domain.description}",
        "paths:",
    ]
    lines.extend(f"  - {path}" for path in domain.paths or ["**"])
    lines.append("topics:")
    lines.extend(f"  - {topic}" for topic in domain.topics or ["general"])
    lines.append("---")
    return "\n".join(lines)


def domain_template(domain: Domain) -> str:
    return (
        domain_frontmatter(domain)
        + "\n\n"
        + dedent(
            f"""
            # {domain.name.title()} Steering

            ## Scope

            {domain.description}

            ## Rules

            - Not yet defined.

            ## Guardrails

            - Keep this file focused; move unrelated rules to another domain file.
            - Record only decisions and conventions that are actually enforced.
            """
        ).strip()
        + "\n"
    )


def write_index(domains: list[str]) -> None:
    domain_rows = []
    for name in domains:
        domain = parse_domain(STEERING / f"{name}.md")
        paths = ", ".join(domain.paths) if domain else "unknown"
        topics = ", ".join(domain.topics) if domain else "unknown"
        domain_rows.append(f"- `{name}.md` — paths: {paths}; topics: {topics}")
    domain_index = "\n".join(domain_rows) or "- None yet"
    content = dedent(
        f"""
        # Steering Index

        Always load:

        - `product.md`
        - `tech.md`
        - `structure.md`

        Load conditionally:

        {domain_index}

        A domain file is relevant when the task touches one of its paths or discusses one of its topics.

        {GENERATED_AT}
        """
    ).strip() + "\n"
    (STEERING / "INDEX.md").write_text(content)


def parse_domain(path: Path) -> Domain | None:
    if not path.exists():
        return None
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None
    frontmatter = match.group(1)
    description = next((line.split(":", 1)[1].strip() for line in frontmatter.splitlines() if line.startswith("description:")), "")
    paths: list[str] = []
    topics: list[str] = []
    section = None
    for line in frontmatter.splitlines():
        if line == "paths:":
            section = "paths"
        elif line == "topics:":
            section = "topics"
        elif line.startswith("  - ") and section:
            (paths if section == "paths" else topics).append(line[4:].strip())
    return Domain(path.stem, description, paths, topics)


def ensure_directory() -> None:
    STEERING.mkdir(parents=True, exist_ok=True)


def init(_args: argparse.Namespace) -> int:
    ensure_directory()
    files = tracked_files()
    (STEERING / "product.md").write_text(product_document(files))
    (STEERING / "tech.md").write_text(technology_document())
    (STEERING / "structure.md").write_text(structure_document(files))
    write_index(domain_names())
    print(f"Initialized steering documents in {STEERING.relative_to(ROOT)}")
    return 0


def refresh(_args: argparse.Namespace) -> int:
    if not (STEERING / "product.md").exists():
        print("Steering directory not initialized; run init first", file=__import__("sys").stderr)
        return 1
    return init(_args)


def domain_names() -> list[str]:
    return sorted(path.stem for path in STEERING.glob("*.md") if path.name not in {"INDEX.md", "product.md", "tech.md", "structure.md"})


def add_domain(args: argparse.Namespace) -> int:
    ensure_directory()
    path = STEERING / f"{args.name}.md"
    if path.exists():
        print(f"Domain already exists: {path.relative_to(ROOT)}", file=__import__("sys").stderr)
        return 1
    domain = Domain(args.name, args.description, args.path, args.topic)
    path.write_text(domain_template(domain))
    write_index(domain_names())
    print(f"Created {path.relative_to(ROOT)} and updated INDEX.md")
    return 0


def doctor(_args: argparse.Namespace) -> int:
    if not STEERING.exists():
        print("FAIL: .kiro/steering does not exist", file=__import__("sys").stderr)
        return 1
    failures = 0
    for required in ("product.md", "tech.md", "structure.md", "INDEX.md"):
        path = STEERING / required
        if not path.exists():
            print(f"FAIL: missing {required}", file=__import__("sys").stderr)
            failures += 1
    domains = domain_names()
    indexed = (STEERING / "INDEX.md").read_text() if (STEERING / "INDEX.md").exists() else ""
    for name in domains:
        path = STEERING / f"{name}.md"
        if f"`{name}.md`" not in indexed:
            print(f"FAIL: {name}.md missing from INDEX.md", file=__import__("sys").stderr)
            failures += 1
        domain = parse_domain(path)
        if not domain or not domain.description or not domain.paths or not domain.topics:
            print(f"FAIL: invalid domain frontmatter in {name}.md", file=__import__("sys").stderr)
            failures += 1
        lines = len(path.read_text().splitlines())
        if lines > 150:
            print(f"FAIL: {name}.md has {lines} lines; keep under 150", file=__import__("sys").stderr)
            failures += 1
    print("Steering doctor:", "PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init").set_defaults(func=init)
    subparsers.add_parser("refresh").set_defaults(func=refresh)
    subparsers.add_parser("doctor").set_defaults(func=doctor)
    domain = subparsers.add_parser("domain")
    domain_subparsers = domain.add_subparsers(dest="domain_command", required=True)
    domain_add = domain_subparsers.add_parser("add")
    domain_add.add_argument("name", help="lowercase slug, e.g. frontend")
    domain_add.add_argument("--description", required=True)
    domain_add.add_argument("--path", action="append", default=[], help="glob or repo path; repeatable")
    domain_add.add_argument("--topic", action="append", default=[], help="topic keyword; repeatable")
    domain_add.set_defaults(func=add_domain)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
