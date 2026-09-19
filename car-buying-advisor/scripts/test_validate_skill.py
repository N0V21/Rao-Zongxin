#!/usr/bin/env python3
"""Tests for scripts/validate_skill.py.

A validator that only ever passes is worthless, so each rule gets a fixture
that must FAIL plus one that must PASS.

Usage::

    python3 scripts/test_validate_skill.py

Exit code 0 = all tests passed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Importing the validator would otherwise leave a __pycache__ directory behind,
# which pollutes the repository when the folder is uploaded directly to GitHub.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_skill import validate  # noqa: E402

FAILURES: list[str] = []
PASSED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILURES.append(f"{label}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


def make_skill(root: Path, dirname: str, body: str) -> Path:
    """Create ``root/dirname/SKILL.md`` with ``body`` and return the dir."""
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


GOOD_DESCRIPTION = "A short valid description of what this skill does and when."


def main() -> int:
    print("validate_skill.py test suite\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # --- happy path ---------------------------------------------------
        print("happy path")
        good = make_skill(
            tmp_path,
            "demo-skill",
            f"---\nname: demo-skill\ndescription: {GOOD_DESCRIPTION}\n---\n\n# Body\n",
        )
        problems, _ = validate(good)
        check("valid skill passes", problems == [], str(problems))

        # --- missing frontmatter -----------------------------------------
        print("\nmissing / malformed frontmatter")
        no_fm = make_skill(tmp_path, "no-fm", "# No frontmatter here\n")
        problems, _ = validate(no_fm)
        check("frontmatter required", len(problems) > 0)

        # --- missing name / description ----------------------------------
        print("\nrequired fields")
        no_name = make_skill(
            tmp_path, "no-name", f"---\ndescription: {GOOD_DESCRIPTION}\n---\n"
        )
        problems, _ = validate(no_name)
        check(
            "missing name rejected",
            any("'name'" in p for p in problems),
            str(problems),
        )

        no_desc = make_skill(tmp_path, "no-desc", "---\nname: no-desc\n---\n")
        problems, _ = validate(no_desc)
        check(
            "missing description rejected",
            any("'description'" in p for p in problems),
            str(problems),
        )

        # --- name rules ---------------------------------------------------
        print("\nname rules")
        mismatch = make_skill(
            tmp_path,
            "dir-name",
            f"---\nname: other-name\ndescription: {GOOD_DESCRIPTION}\n---\n",
        )
        problems, _ = validate(mismatch)
        check(
            "name must match directory",
            any("directory name" in p for p in problems),
            str(problems),
        )

        bad_chars = make_skill(
            tmp_path,
            "bad_chars",
            f"---\nname: bad_chars\ndescription: {GOOD_DESCRIPTION}\n---\n",
        )
        problems, _ = validate(bad_chars)
        check(
            "underscores rejected in name",
            any("lowercase letters" in p for p in problems),
            str(problems),
        )

        long_name = make_skill(
            tmp_path,
            "a" * 65,
            f"---\nname: {'a' * 65}\ndescription: {GOOD_DESCRIPTION}\n---\n",
        )
        problems, _ = validate(long_name)
        check(
            "name over 64 chars rejected",
            any("max is 64" in p for p in problems),
            str(problems),
        )

        trailing = make_skill(
            tmp_path,
            "trailing-",
            f"---\nname: trailing-\ndescription: {GOOD_DESCRIPTION}\n---\n",
        )
        problems, _ = validate(trailing)
        check(
            "trailing hyphen rejected",
            any("lowercase letters" in p for p in problems),
            str(problems),
        )

        # --- description length -------------------------------------------
        print("\ndescription length")
        too_long = make_skill(
            tmp_path,
            "long-desc",
            f"---\nname: long-desc\ndescription: {'x' * 1025}\n---\n",
        )
        problems, _ = validate(too_long)
        check(
            "description over 1024 rejected",
            any("max is 1024" in p for p in problems),
            str(problems),
        )

        exact = make_skill(
            tmp_path,
            "exact-desc",
            f"---\nname: exact-desc\ndescription: {'x' * 1024}\n---\n",
        )
        problems, _ = validate(exact)
        check("description of exactly 1024 accepted", problems == [], str(problems))

        # --- compatibility length -----------------------------------------
        print("\noptional fields")
        compat_long = make_skill(
            tmp_path,
            "compat-long",
            f"---\nname: compat-long\ndescription: {GOOD_DESCRIPTION}\n"
            f"compatibility: {'y' * 501}\n---\n",
        )
        problems, _ = validate(compat_long)
        check(
            "compatibility over 500 rejected",
            any("max is 500" in p for p in problems),
            str(problems),
        )

        # --- resource references ------------------------------------------
        print("\nresource references")
        missing_ref = make_skill(
            tmp_path,
            "missing-ref",
            f"---\nname: missing-ref\ndescription: {GOOD_DESCRIPTION}\n---\n\n"
            "See `references/nope.md` for details.\n",
        )
        problems, _ = validate(missing_ref)
        check(
            "dangling resource reference rejected",
            any("does not exist" in p for p in problems),
            str(problems),
        )

        existing_ref = make_skill(
            tmp_path,
            "existing-ref",
            f"---\nname: existing-ref\ndescription: {GOOD_DESCRIPTION}\n---\n\n"
            "See `references/yes.md` for details.\n",
        )
        (existing_ref / "references").mkdir()
        (existing_ref / "references" / "yes.md").write_text("hi", encoding="utf-8")
        problems, _ = validate(existing_ref)
        check("resolvable resource reference accepted", problems == [], str(problems))

        # --- nested metadata must not break parsing ------------------------
        print("\nnested frontmatter mappings")
        nested = make_skill(
            tmp_path,
            "nested-meta",
            f"---\nname: nested-meta\ndescription: {GOOD_DESCRIPTION}\n"
            "metadata:\n  version: 1.0.0\n  language: zh-CN\n---\n",
        )
        problems, _ = validate(nested)
        check("nested metadata parses cleanly", problems == [], str(problems))

    print(f"\n{PASSED} passed, {len(FAILURES)} failed")
    if FAILURES:
        for failure in FAILURES:
            print(f"  FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
