#!/usr/bin/env python3
"""Validate a skill directory against the Agent Skills specification.

Spec: https://agentskills.io/specification

Usage::

    python3 scripts/validate_skill.py              # validate this repository
    python3 scripts/validate_skill.py path/to/skill

Checks:
  * SKILL.md exists and starts with a YAML frontmatter block
  * required fields ``name`` and ``description`` are present
  * ``name`` is <= 64 chars, lowercase letters/digits/hyphens, no leading or
    trailing hyphen, and matches the containing directory name
  * ``description`` is non-empty and <= 1024 chars
  * optional ``compatibility`` is <= 500 chars when present
  * every relative resource path referenced from the body exists on disk

No third-party dependencies: the frontmatter parser is deliberately minimal so
this runs on a bare ``python3`` in CI.

Exit code 0 = valid, 1 = problems found, 2 = bad invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

NAME_RE_TEMPLATE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
NAME_MAX = 64

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (top-level scalar fields, body).

    Only top-level ``key: value`` pairs are read; nested mappings (such as
    ``metadata:``) are skipped, which is all the checks below require.
    """
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text

    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        fields[key.strip()] = value.strip().strip('"').strip("'")

    return fields, "\n".join(lines[end + 1 :])


def validate(root: Path) -> tuple[list[str], list[str]]:
    """Return (problems, notes) for the skill directory ``root``."""
    import re

    name_re = re.compile(NAME_RE_TEMPLATE)
    resource_re = re.compile(
        r"`\.?/?((?:references|assets|examples|scripts)/[^`\s]+?)`"
    )

    problems: list[str] = []
    notes: list[str] = []

    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        return [f"SKILL.md not found in {root}"], notes

    text = skill_path.read_text(encoding="utf-8")
    fields, body = parse_frontmatter(text)

    if not fields:
        problems.append("SKILL.md does not start with a valid YAML frontmatter block")

    name = fields.get("name", "")
    if not name:
        problems.append("frontmatter is missing the required field 'name'")
    else:
        if len(name) > NAME_MAX:
            problems.append(f"'name' is {len(name)} chars, max is {NAME_MAX}")
        if not name_re.match(name):
            problems.append(
                "'name' must be lowercase letters, digits and hyphens only, "
                "and must not start or end with a hyphen"
            )
        if name != root.name:
            problems.append(
                f"'name' ({name!r}) must match the directory name ({root.name!r})"
            )

    description = fields.get("description", "")
    if not description:
        problems.append("frontmatter is missing the required field 'description'")
    elif len(description) > DESCRIPTION_MAX:
        problems.append(
            f"'description' is {len(description)} chars, max is {DESCRIPTION_MAX}"
        )
    else:
        notes.append(f"description length: {len(description)}/{DESCRIPTION_MAX}")

    compatibility = fields.get("compatibility", "")
    if compatibility and len(compatibility) > COMPATIBILITY_MAX:
        problems.append(
            f"'compatibility' is {len(compatibility)} chars, "
            f"max is {COMPATIBILITY_MAX}"
        )

    referenced = sorted(set(resource_re.findall(body)))
    if not referenced:
        notes.append("no relative resource paths referenced from the body")
    for relative in referenced:
        if (root / relative).is_file():
            notes.append(f"ok  {relative}")
        else:
            problems.append(f"body references '{relative}' but that file does not exist")

    return problems, notes


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("usage: validate_skill.py [SKILL_DIR]", file=sys.stderr)
        return 2

    root = Path(argv[1]).resolve() if len(argv) == 2 else REPO_ROOT

    problems, notes = validate(root)

    for note in notes:
        print(f"  {note}")
    if problems:
        print()
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    print(f"\nOK: {root.name} conforms to the Agent Skills specification")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
