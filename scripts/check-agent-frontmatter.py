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

# Kept in sync by hand with Claude Code's built-in tool names. Update this
# set when a new built-in tool ships — an unrecognized-but-legitimate name
# is reported as an error rather than silently accepted (see check_file).
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

# A YAML block list: `tools:` on its own line, followed by one or more
# `  - Item` lines.
_BLOCK_LIST_RE = re.compile(r"^tools:[ \t]*\r?\n((?:^[ \t]+-[ \t]*.+\r?\n?)+)", re.MULTILINE)
_INLINE_RE = re.compile(r"^tools:[ \t]*(.+)$", re.MULTILINE)


def extract_tools_tokens(text: str) -> list[str] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    frontmatter = text[3:end]

    block_match = _BLOCK_LIST_RE.search(frontmatter)
    if block_match:
        items = re.findall(r"^[ \t]+-[ \t]*(.+?)\s*$", block_match.group(1), re.MULTILINE)
        return [item.strip() for item in items if item.strip()]

    inline_match = _INLINE_RE.search(frontmatter)
    if inline_match:
        raw = inline_match.group(1).strip().strip("[]")
        return [t.strip().strip("[]").strip() for t in raw.split(",") if t.strip()]

    return None


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    tokens = extract_tools_tokens(path.read_text())
    if tokens is None:
        errors.append(f"{path}: no `tools:` frontmatter field found")
        return errors

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
