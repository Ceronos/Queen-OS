"""Read-only check for missing local Markdown link targets.

Run: python scripts/check_local_markdown_links.py [directory]
Only checks ordinary inline links; remote URLs and fragment-only links are skipped.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\((<[^>]+>|[^)\s]+)(?:\s+['\"][^)]*['\"])?\)")


def missing_targets(root: Path) -> list[str]:
    """Return sorted missing relative targets without modifying any files."""
    root = root.resolve()
    missing: list[str] = []
    for source in sorted(root.rglob("*.md")):
        if not source.is_file():
            continue
        for match in _LINK.finditer(source.read_text(encoding="utf-8")):
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path or target.startswith("//"):
                continue
            path = (source.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(root):
                continue  # Outside the checked tree: do not traverse it.
            if not path.exists():
                missing.append(f"{source.relative_to(root)}: {target}")
    return sorted(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error("directory must exist")
    missing = missing_targets(args.directory)
    for entry in missing:
        print(entry)
    print(f"{len(missing)} missing local Markdown target(s)")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
