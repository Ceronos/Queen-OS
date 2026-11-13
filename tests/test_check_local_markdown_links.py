"""Offline tests for the read-only Markdown link checker."""

import tempfile
import unittest
from pathlib import Path

from scripts.check_local_markdown_links import missing_targets


class LinkCheckTests(unittest.TestCase):
    def test_existing_missing_external_and_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "ok.md").write_text("ok", encoding="utf-8")
            (root / "README.md").write_text(
                "[ok](docs/ok.md) [missing](docs/no.md) [web](https://example.org) "
                "[anchor](#intro) [encoded](docs/ok.md#heading)", encoding="utf-8"
            )
            self.assertEqual(missing_targets(root), ["README.md: docs/no.md"])

    def test_encoded_spaces_and_nested_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "a b.md").write_text("ok", encoding="utf-8")
            (root / "docs" / "index.md").write_text(
                "[space](../a%20b.md) [absent](../missing.md)", encoding="utf-8"
            )
            self.assertEqual(missing_targets(root), ["docs/index.md: ../missing.md"])

    def test_inline_and_fenced_code_not_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "`[inline](missing-inline.md)`\n"
                "```md\n[fenced](missing-fenced.md)\n```\n"
                "~~~md\n[tilde](missing-tilde.md)\n~~~\n"
                "[real](missing-real.md)\n", encoding="utf-8"
            )
            self.assertEqual(missing_targets(root), ["README.md: missing-real.md"])


    def test_fence_closer_with_trailing_text_is_not_a_closer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "```python\n"
                "```not-a-closer\n"
                "[fake](missing-fake.md)\n"
                "```\n"
                "[real](missing-real.md)\n", encoding="utf-8"
            )
            self.assertEqual(missing_targets(root), ["README.md: missing-real.md"])


    def test_indented_closing_fences_restore_prose(self):
        for indent in (1, 2, 3):
            for delimiter in (chr(96) * 3, "~~~"):
                with (
                    self.subTest(indent=indent, delimiter=delimiter),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    root = Path(tmp)
                    (root / "README.md").write_text(
                        f"{delimiter}python\n"
                        "[fake](missing-fake.md)\n"
                        + " " * indent + f"{delimiter}\n"
                        + "[real](missing-real.md)\n",
                        encoding="utf-8",
                    )
                    self.assertEqual(
                        missing_targets(root), ["README.md: missing-real.md"]
                    )


if __name__ == "__main__":
    unittest.main()
