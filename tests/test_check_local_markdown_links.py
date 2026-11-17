"""Offline tests for the read-only Markdown link checker."""

import runpy
import tempfile
import unittest
from pathlib import Path

# The checker is a standalone script, not an installed Python package.
# Resolve it from this test file so pytest collection works without repo-root PYTHONPATH.
missing_targets = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "check_local_markdown_links.py")
)["missing_targets"]


class LinkCheckTests(unittest.TestCase):
    def test_existing_missing_external_and_fragment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "ok.md").write_text("ok", encoding="utf-8")
            (root / "README.md").write_text(
                "[ok](docs/ok.md) [missing](docs/no.md) [web](https://example.org) "
                "[anchor](#intro) [encoded](docs/ok.md#heading)",
                encoding="utf-8",
            )
            self.assertEqual(missing_targets(root), ["README.md: docs/no.md"])

    def test_encoded_spaces_and_nested_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "a b.md").write_text("ok", encoding="utf-8")
            (root / "docs" / "index.md").write_text("[space](../a%20b.md) [absent](../missing.md)", encoding="utf-8")
            self.assertEqual(missing_targets(root), ["docs/index.md: ../missing.md"])

    def test_inline_and_fenced_code_not_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "`[inline](missing-inline.md)`\n"
                "```md\n[fenced](missing-fenced.md)\n```\n"
                "~~~md\n[tilde](missing-tilde.md)\n~~~\n"
                "[real](missing-real.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(missing_targets(root), ["README.md: missing-real.md"])

    def test_fence_closer_with_trailing_text_is_not_a_closer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "```python\n```not-a-closer\n[fake](missing-fake.md)\n```\n[real](missing-real.md)\n", encoding="utf-8"
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
                        "[fake](missing-fake.md)\n" + " " * indent + f"{delimiter}\n" + "[real](missing-real.md)\n",
                        encoding="utf-8",
                    )
                    self.assertEqual(missing_targets(root), ["README.md: missing-real.md"])

    def test_a081_tab_indented_fences_do_not_hide_links(self):
        for leading in ("\t", " \t", "  \t"):
            with (
                self.subTest(leading=repr(leading)),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "README.md").write_text(
                    f"{leading}```python\n[visible](missing-visible.md)\n",
                    encoding="utf-8",
                )
                self.assertEqual(missing_targets(root), ["README.md: missing-visible.md"])

    def test_a081_invalid_backtick_info_strings_do_not_hide_links(self):
        for opener in ("```python`bad", "```` ` ", "```lang`"):
            with (
                self.subTest(opener=opener),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "README.md").write_text(
                    f"{opener}\n[visible](missing-visible.md)\n",
                    encoding="utf-8",
                )
                self.assertEqual(missing_targets(root), ["README.md: missing-visible.md"])

    def test_a081_unequal_inline_backtick_runs_do_not_hide_links(self):
        for snippet in ("`[visible](missing-visible.md)``", "``[visible](missing-visible.md)`"):
            with (
                self.subTest(snippet=snippet),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "README.md").write_text(f"{snippet}\n", encoding="utf-8")
                self.assertEqual(missing_targets(root), ["README.md: missing-visible.md"])

    def test_a081_valid_fences_and_equal_inline_runs_still_mask_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "   ```python\n[hidden](missing-fence.md)\n```\n"
                "~~~lang`extra\n[hidden](missing-tilde.md)\n~~~\n"
                "`[hidden](missing-inline.md)`\n"
                "``[hidden](missing-double.md)``\n"
                "[visible](missing-visible.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(missing_targets(root), ["README.md: missing-visible.md"])

    def test_a081_unmatched_backticks_do_not_pair_across_paragraphs(self):
        for blank_line in ("\n", " \t\n"):
            with (
                self.subTest(blank_line=repr(blank_line)),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                (root / "README.md").write_text(
                    "```text\n[hidden](missing-fenced.md)\n```\n"
                    "`unmatched opener in first paragraph\n"
                    + blank_line
                    + "[visible](missing-between.md)\n"
                    + blank_line
                    + "`unmatched run in third paragraph\n",
                    encoding="utf-8",
                )
                self.assertEqual(
                    missing_targets(root), ["README.md: missing-between.md"]
                )

    def test_a081_many_distinct_unmatched_runs_preserve_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unmatched_runs = "\n".join("`" * length for length in range(1, 257))
            (root / "README.md").write_text(
                unmatched_runs + "\n[visible](missing-visible.md)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                missing_targets(root), ["README.md: missing-visible.md"]
            )


if __name__ == "__main__":
    unittest.main()
