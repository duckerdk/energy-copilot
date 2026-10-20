#!/usr/bin/env python3
"""Validate local Markdown links and required Codex entry points (standard library only)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)]+)\)")
REQUIRED = (
    "README.md",
    "AGENTS.md",
    "requirements/OPEN_ITEMS.md",
    "requirements/TEST_SCENARIOS.md",
)
DEPRECATED = (
    "requirements/DEVELOPER_HANDOFF.md",
    "requirements/HA_READONLY_CAPTURE.md",
    "requirements/HA_TIMESERIES_CAPTURE.md",
)


def main() -> int:
    errors: list[str] = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"missing required file: {name}")

    for name in DEPRECATED:
        if (ROOT / name).exists():
            errors.append(f"obsolete file reintroduced: {name}")

    checked = 0
    for document in sorted(ROOT.rglob("*.md")):
        if ".git" in document.parts or ".venv" in document.parts:
            continue
        body = document.read_text(encoding="utf-8")
        for match in LINK.finditer(body):
            raw_target = match.group(1).strip()
            # Support optional Markdown titles: (path "Title").
            target = raw_target.split(" ", 1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            rel = unquote(parsed.path)
            if not rel:
                continue
            destination = ((ROOT if rel.startswith("/") else document.parent) / rel.lstrip("/")).resolve()
            try:
                destination.relative_to(ROOT)
            except ValueError:
                errors.append(f"{document.relative_to(ROOT)}: link outside repository: {target}")
                continue
            if not destination.is_file():
                line = body.count("\n", 0, match.start()) + 1
                errors.append(f"{document.relative_to(ROOT)}:{line}: missing link target {target}")
            checked += 1

    if errors:
        for issue in errors:
            print(f"ERROR: {issue}", file=sys.stderr)
        print(f"Documentation check failed: {len(errors)} issue(s).", file=sys.stderr)
        return 1
    print(f"Documentation check passed ({checked} local links; no obsolete files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
