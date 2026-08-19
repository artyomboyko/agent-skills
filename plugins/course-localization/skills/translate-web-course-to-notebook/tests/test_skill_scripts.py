import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


normalize_cells = load_script("normalize_notebook_cells")
normalize_terms = load_script("normalize_repository_visibility_terms")


class NormalizeNotebookCellsTests(unittest.TestCase):
    def notebook(self, first_metadata, second_metadata):
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "first",
                    "metadata": first_metadata,
                    "source": ["First block"],
                },
                {
                    "cell_type": "markdown",
                    "id": "second",
                    "metadata": second_metadata,
                    "source": ["Second block"],
                },
            ],
            "metadata": {"language_info": {"name": "python"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    def test_merges_adjacent_content_when_metadata_matches(self):
        notebook = self.notebook({"tags": ["course"]}, {"tags": ["course"]})

        normalized = normalize_cells.normalized_notebook(notebook)

        self.assertEqual(len(normalized["cells"]), 1)
        self.assertEqual(normalized["cells"][0]["id"], "first")
        self.assertEqual(normalized["cells"][0]["metadata"], {"tags": ["course"]})
        self.assertEqual(
            normalized["cells"][0]["source"],
            ["First block\n", "\n", "Second block"],
        )
        self.assertEqual(normalized["metadata"], notebook["metadata"])

    def test_rejects_adjacent_content_when_metadata_differs(self):
        notebook = self.notebook({"tags": ["first"]}, {"tags": ["second"]})

        with self.assertRaisesRegex(ValueError, "cannot merge adjacent Markdown"):
            normalize_cells.normalized_notebook(notebook)


class NormalizeRepositoryVisibilityTermsTests(unittest.TestCase):
    def test_normalizes_prose_only_and_preserves_code_byte_for_byte(self):
        fenced = "```python\nпубличный репозиторий\n```"
        inline = "`закрытый репозиторий`"
        text = (
            "публичный репозиторий\n"
            f"{fenced}\n"
            f"{inline} и закрытый репозиторий\n"
            "~~~\n"
            "внутренний репозиторий\n"
            "~~~\n"
        )

        normalized, changes = normalize_terms.normalize_markdown_text(text)

        self.assertEqual(changes, 2)
        self.assertIn(fenced, normalized)
        self.assertIn(inline, normalized)
        self.assertIn("публичный репозиторий (public repository)", normalized)
        self.assertIn("частный репозиторий (private repository)", normalized)
        self.assertNotIn("закрытый репозиторий (private repository)", normalized)
        self.assertNotIn("внутренний репозиторий (internal repository)", normalized)

    def test_preserves_fence_inside_one_source_element(self):
        source = ["Outside публичный репозиторий\n```text\nпубличный репозиторий\n```\n"]

        normalized, changes = normalize_terms.normalize_markdown_source(source)

        self.assertEqual(changes, 1)
        self.assertEqual(
            normalized,
            ["Outside публичный репозиторий (public repository)\n```text\nпубличный репозиторий\n```\n"],
        )

    def test_carries_fence_state_across_source_elements(self):
        source = ["```text\nпубличный репозиторий\n", "закрытый репозиторий\n```\n"]

        normalized, changes = normalize_terms.normalize_markdown_source(source)

        self.assertEqual(changes, 0)
        self.assertEqual(normalized, source)

    def test_preserves_source_element_boundaries(self):
        source = [
            "публичный репозиторий\n",
            "```text\nпубличный репозиторий\n```\n",
            "закрытый репозиторий",
        ]

        normalized, _ = normalize_terms.normalize_markdown_source(source)

        self.assertEqual(len(normalized), len(source))
        self.assertEqual([item.count("\n") for item in normalized], [1, 3, 0])


if __name__ == "__main__":
    unittest.main()
