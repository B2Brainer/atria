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

_TOP_LEVEL_KEY_RE = re.compile(r"^tools:[ \t]*(.*?)[ \t]*$")
_LIST_ITEM_RE = re.compile(r"^[ \t]+-[ \t]*(.+?)[ \t]*$")


def _unquote(token: str) -> str:
    token = token.strip().strip("[]").strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        token = token[1:-1]
    return token.strip()


def extract_tools_tokens(text: str) -> list[str] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    lines = text[3:end].splitlines()

    # A `tools:` key (block scalar or inline value) may appear more than
    # once in malformed frontmatter; YAML's own rule is last-key-wins, so
    # scan for every top-level occurrence and keep only the last.
    tools_line_index: int | None = None
    inline_value = ""
    for i, line in enumerate(lines):
        match = _TOP_LEVEL_KEY_RE.match(line)
        if match:
            tools_line_index = i
            inline_value = match.group(1)

    if tools_line_index is None:
        return None

    if inline_value and not inline_value.lstrip().startswith("#"):
        raw = inline_value.strip().strip("[]")
        return [_unquote(t) for t in raw.split(",") if t.strip()]

    # Block-scalar form: `tools:` (optionally followed by blank/comment
    # lines) then one or more `  - Item` lines. Blank and comment lines
    # inside the block are skipped, not treated as its end — the block
    # ends only at the first line that is non-blank, non-comment, and not
    # a list item (typically the next top-level key, or EOF).
    items: list[str] = []
    for line in lines[tools_line_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item_match = _LIST_ITEM_RE.match(line)
        if item_match is None:
            break
        items.append(_unquote(item_match.group(1)))

    return [item for item in items if item]


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
