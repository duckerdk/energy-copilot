#!/usr/bin/env python3
"""Ensure canonical documentation layout and resolvable local Markdown links."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import re
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "README.md", "AGENTS.md",
    "requirements/REQUIREMENTS.md", "requirements/HA_CONTRACT.md",
    "requirements/OPTIMIZATION.md", "requirements/EXECUTION.md",
    "requirements/VALIDATION.md", "requirements/OPEN_ITEMS.md",
}
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)]+)\)")
def main():
    errors = []
    # Ignore local virtualenv/test caches, including their generated README files.
    all_md = set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT, text=True,
    ).splitlines())
    if all_md != EXPECTED:
        errors.append(f"Markdown layout mismatch: extra={sorted(all_md-EXPECTED)} missing={sorted(EXPECTED-all_md)}")
    count = 0
    for filename in sorted(EXPECTED & all_md):
        p = ROOT / filename
        body = p.read_text(encoding="utf-8")
        for m in LINK.finditer(body):
            target = m.group(1).split(" ", 1)[0].strip("<>")
            u = urlsplit(target)
            if u.scheme or u.netloc or target.startswith("#") or not u.path:
                continue
            dest = (p.parent / unquote(u.path)).resolve()
            if not dest.is_relative_to(ROOT) or not dest.is_file():
                errors.append(f"{filename}: invalid link {target}")
            count += 1
    if errors:
        print("\n".join(errors),file=sys.stderr)
        return 1
    print(f"Documentation check passed ({len(all_md)} Markdown files, {count} links)")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
