#!/usr/bin/env python3
"""Validates .claude/agents/*.md frontmatter `tools:` casing.

Guards against the recurrence of the code-reviewer-tools-lowercase-bug
gotcha: `tools: [read, glob, grep, bash]` (lowercase) silently spawns an
agent with zero tools instead of the four intended ones, and the failure
is invisible until someone invokes the agent in a session.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KNOWN_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "Bash",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Agent",
    "Artifact",
}
KNOWN_TOOLS_LOWER = {t.lower(): t for t in KNOWN_TOOLS}

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"


def extract_tools_line(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    frontmatter = text[3:end]
    match = re.search(r"^tools:\s*(.+)$", frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else None


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    raw = extract_tools_line(path.read_text())
    if raw is None:
        errors.append(f"{path}: no `tools:` frontmatter field found")
        return errors

    tokens = [t.strip().strip("[]").strip() for t in raw.strip("[]").split(",")]
    tokens = [t for t in tokens if t]
    if not tokens:
        errors.append(f"{path}: `tools:` field is empty")
        return errors

    for token in tokens:
        if token in KNOWN_TOOLS:
            continue
        if token.lower() in KNOWN_TOOLS_LOWER:
            errors.append(
                f"{path}: tool '{token}' is miscased — the agent registry expects "
                f"'{KNOWN_TOOLS_LOWER[token.lower()]}'. A miscased entry spawns the "
                f"agent with zero tools."
            )
        else:
            errors.append(f"{path}: unrecognized tool '{token}' in `tools:` field")
    return errors


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"no {AGENTS_DIR} directory — nothing to check")
        return 0

    all_errors: list[str] = []
    for path in sorted(AGENTS_DIR.glob("*.md")):
        all_errors.extend(check_file(path))

    if all_errors:
        for error in all_errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"ok: {len(list(AGENTS_DIR.glob('*.md')))} agent file(s) have valid `tools:` frontmatter")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
