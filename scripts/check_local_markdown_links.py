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
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")
_BACKTICK_RUN = re.compile(r"`+")


def _mask_inline_code(content: str) -> str:
    """Mask only code spans delimited by equal-length backtick runs."""
    runs = list(_BACKTICK_RUN.finditer(content))
    masked: list[str] = []
    cursor = 0
    i = 0
    while i < len(runs):
        j = i + 1
        while j < len(runs) and len(runs[j].group()) != len(runs[i].group()):
            j += 1
        if j == len(runs):
            i += 1
            continue
        masked.append(content[cursor : runs[i].start()])
        masked.append(" " * (runs[j].end() - runs[i].start()))
        cursor = runs[j].end()
        i = j + 1
    masked.append(content[cursor:])
    return "".join(masked)


def _prose_only(content: str) -> str:
    """Mask fenced blocks and exact-run inline code while retaining ordinary links."""
    chunks: list[str] = []
    prose: list[str] = []
    fence_char = ""
    fence_length = 0
    for line in content.splitlines(keepends=True):
        marker = _FENCE.match(line.rstrip("\r\n"))
        if fence_char:
            if (
                marker
                and marker.group(1)[0] == fence_char
                and len(marker.group(1)) >= fence_length
                and not marker.group(2).strip()
            ):
                fence_char = ""
                fence_length = 0
            chunks.append("\n")
            continue
        if marker and (marker.group(1).startswith("~") or "`" not in marker.group(2)):
            if prose:
                chunks.append(_mask_inline_code("".join(prose)))
                prose.clear()
            fence_char = marker.group(1)[0]
            fence_length = len(marker.group(1))
            chunks.append("\n")
            continue
        prose.append(line)
    if prose:
        chunks.append(_mask_inline_code("".join(prose)))
    return "".join(chunks)


def missing_targets(root: Path) -> list[str]:
    """Return sorted missing relative targets without modifying any files."""
    root = root.resolve()
    missing: list[str] = []
    for source in sorted(root.rglob("*.md")):
        if not source.is_file():
            continue
        for match in _LINK.finditer(_prose_only(source.read_text(encoding="utf-8"))):
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path or target.startswith("//"):
                continue
            path = (source.parent / unquote(parsed.path)).resolve()
            if not path.is_relative_to(root):
                continue  # Outside the checked tree: do not traverse it.
            if not path.exists():
                missing.append(f"{source.relative_to(root).as_posix()}: {target}")
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
