"""Issue #40: ATX headings must separate inline-code delimiter pairing."""

import runpy
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_local_markdown_links.py"
missing_targets = runpy.run_path(str(CHECKER))["missing_targets"]


def test_adjacent_h2_does_not_pair_backticks_across_heading():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text(
            "`opening paragraph\n## Heading\n[visible](missing-heading.md)\n`closing paragraph\n",
            encoding="utf-8",
        )
        assert missing_targets(root) == ["README.md: missing-heading.md"]


def test_blank_separated_h2_control():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text(
            "`opening paragraph\n\n## Heading\n[visible](missing-heading.md)\n\n`closing paragraph\n",
            encoding="utf-8",
        )
        assert missing_targets(root) == ["README.md: missing-heading.md"]
