"""Unit tests for scripts/check-agent-frontmatter.py's frontmatter parser."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check-agent-frontmatter.py"
_spec = importlib.util.spec_from_file_location("check_agent_frontmatter", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_agent_frontmatter = importlib.util.module_from_spec(_spec)
sys.modules["check_agent_frontmatter"] = check_agent_frontmatter
_spec.loader.exec_module(check_agent_frontmatter)

extract_tools_tokens = check_agent_frontmatter.extract_tools_tokens
check_file = check_agent_frontmatter.check_file


def _frontmatter(tools_block: str) -> str:
    return f"---\nname: x\n{tools_block}\nmodel: inherit\n---\n\nbody\n"


def test_extract_inline_comma_list():
    text = _frontmatter("tools: Read, Glob, Grep, Bash")
    assert extract_tools_tokens(text) == ["Read", "Glob", "Grep", "Bash"]


def test_extract_inline_bracket_list():
    text = _frontmatter("tools: [Read, Glob, Grep, Bash]")
    assert extract_tools_tokens(text) == ["Read", "Glob", "Grep", "Bash"]


def test_extract_yaml_block_list():
    text = _frontmatter("tools:\n  - Read\n  - Glob\n  - Grep\n  - Bash")
    assert extract_tools_tokens(text) == ["Read", "Glob", "Grep", "Bash"]


def test_no_tools_field_returns_none():
    text = "---\nname: x\nmodel: inherit\n---\n\nbody\n"
    assert extract_tools_tokens(text) is None


def test_check_file_detects_miscased_tool(tmp_path):
    path = tmp_path / "agent.md"
    path.write_text(_frontmatter("tools: read, glob, grep, bash"))
    errors = check_file(path)
    assert len(errors) == 4
    assert all("miscased" in e for e in errors)


def test_check_file_accepts_block_list(tmp_path):
    path = tmp_path / "agent.md"
    path.write_text(_frontmatter("tools:\n  - Read\n  - Glob"))
    assert check_file(path) == []


def test_check_file_rejects_unrecognized_tool(tmp_path):
    path = tmp_path / "agent.md"
    path.write_text(_frontmatter("tools: Read, NotARealTool"))
    errors = check_file(path)
    assert len(errors) == 1
    assert "unrecognized tool 'NotARealTool'" in errors[0]
