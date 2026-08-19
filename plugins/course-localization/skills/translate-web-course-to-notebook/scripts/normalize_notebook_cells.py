#!/usr/bin/env python3
"""Normalize translated course Markdown cells in a Jupyter notebook."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote


HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+\S.*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LOCAL_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Put every Markdown heading in its own cell and merge the content "
            "until the next heading into one following cell."
        )
    )
    parser.add_argument("notebook", type=Path, help="Path to the .ipynb file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate normalization without changing the notebook",
    )
    parser.add_argument(
        "--validate-images",
        action="store_true",
        help="Fail when a relative Markdown image target is missing",
    )
    return parser.parse_args()


def is_heading_line(line: str, fence: tuple[str, int] | None) -> bool:
    return fence is None and bool(HEADING_RE.match(line))


def update_fence(line: str, fence: tuple[str, int] | None) -> tuple[str, int] | None:
    match = FENCE_RE.match(line)
    if not match:
        return fence
    marker = match.group(1)
    candidate = (marker[0], len(marker))
    if fence is None:
        return candidate
    if candidate[0] == fence[0] and candidate[1] >= fence[1]:
        return None
    return fence


def split_markdown(text: str) -> list[tuple[str, str]]:
    """Return ordered (kind, text) segments; headings never include body text."""
    segments: list[tuple[str, str]] = []
    content: list[str] = []
    fence: tuple[str, int] | None = None

    def flush_content() -> None:
        block = "".join(content).strip()
        content.clear()
        if block:
            segments.append(("content", block))

    for line in text.splitlines(keepends=True):
        clean = line.rstrip("\r\n")
        if is_heading_line(clean, fence):
            flush_content()
            segments.append(("heading", clean.strip()))
            continue
        content.append(line)
        fence = update_fence(clean, fence)

    flush_content()
    return segments


def make_cell(original: dict, source: str, cell_id: str) -> dict:
    cell = copy.deepcopy(original)
    cell["cell_type"] = "markdown"
    cell["id"] = cell_id
    cell["source"] = source.splitlines(keepends=True) or [source]
    return cell


def new_id(used_ids: set[str]) -> str:
    while True:
        candidate = uuid.uuid4().hex[:8]
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate


def mergeable_content_cells(first: dict, second: dict) -> bool:
    first_properties = {key: value for key, value in first.items() if key not in {"id", "source"}}
    second_properties = {key: value for key, value in second.items() if key not in {"id", "source"}}
    return first_properties == second_properties


def normalized_notebook(notebook: dict) -> dict:
    result = copy.deepcopy(notebook)
    original_cells = notebook.get("cells")
    if not isinstance(original_cells, list):
        raise ValueError("Notebook must contain a cells array")

    used_ids: set[str] = set()
    output: list[tuple[dict, str]] = []

    for original in original_cells:
        if original.get("cell_type") != "markdown":
            cell = copy.deepcopy(original)
            cell_id = cell.get("id")
            if not isinstance(cell_id, str) or not cell_id or cell_id in used_ids:
                cell["id"] = new_id(used_ids)
            else:
                used_ids.add(cell_id)
            output.append((cell, "other"))
            continue

        source = original.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source)
        segments = split_markdown(text)
        if not segments:
            continue

        original_id = original.get("id")
        for index, (kind, block) in enumerate(segments):
            if (
                index == 0
                and isinstance(original_id, str)
                and original_id
                and original_id not in used_ids
            ):
                cell_id = original_id
                used_ids.add(cell_id)
            else:
                cell_id = new_id(used_ids)
            cell = make_cell(original, block, cell_id)

            if output and kind == "content" and output[-1][1] == "content":
                previous, _ = output[-1]
                if not mergeable_content_cells(previous, cell):
                    raise ValueError(
                        "cannot merge adjacent Markdown content cells without losing metadata"
                    )
                combined = "".join(previous.get("source", [])).strip()
                combined += "\n\n" + block.strip()
                previous["source"] = combined.splitlines(keepends=True)
            else:
                output.append((cell, kind))

    result["cells"] = [cell for cell, _ in output]
    return result


def validate_structure(notebook: dict) -> list[str]:
    errors: list[str] = []
    previous_kind: str | None = None
    ids: set[str] = set()

    if notebook.get("nbformat") != 4:
        errors.append("unsupported or missing nbformat; expected 4")
    if not isinstance(notebook.get("nbformat_minor"), int):
        errors.append("missing integer nbformat_minor")

    for index, cell in enumerate(notebook.get("cells", [])):
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or not cell_id:
            errors.append(f"cell {index}: missing id")
        elif cell_id in ids:
            errors.append(f"cell {index}: duplicate id {cell_id}")
        else:
            ids.add(cell_id)

        if cell.get("cell_type") != "markdown":
            previous_kind = "other"
            continue

        source = cell.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source)
        fence: tuple[str, int] | None = None
        for line in text.splitlines():
            fence = update_fence(line, fence)
        if fence is not None:
            errors.append(f"cell {index}: unclosed fenced code block")
        segments = split_markdown(text)
        if len(segments) != 1:
            errors.append(f"cell {index}: contains mixed headings or content")
            previous_kind = "mixed"
            continue

        kind, _ = segments[0]
        if kind == "content" and previous_kind == "content":
            errors.append(f"cells {index - 1}/{index}: adjacent content blocks")
        previous_kind = kind

    return errors


def image_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " " in target:
        target = target.split(" ", 1)[0]
    return target


def missing_images(notebook: dict, notebook_path: Path) -> list[str]:
    missing: list[str] = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", [])
        text = "".join(source) if isinstance(source, list) else str(source)
        for match in LOCAL_IMAGE_RE.finditer(text):
            target = image_target(match.group(1))
            lowered = target.lower()
            if lowered.startswith(("http://", "https://", "data:", "attachment:", "#")):
                continue
            relative = unquote(target).replace("/", "\\" if sys.platform == "win32" else "/")
            if not (notebook_path.parent / relative).exists():
                missing.append(target)
    return sorted(set(missing))


def main() -> int:
    args = parse_args()
    path = args.notebook.resolve()
    if not path.is_file():
        print(f"error: notebook not found: {path}", file=sys.stderr)
        return 2

    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        normalized = normalized_notebook(notebook)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    errors = validate_structure(normalized)
    if args.validate_images:
        missing = missing_images(normalized, path)
        errors.extend(f"missing image: {target}" for target in missing)

    if args.check and notebook.get("cells") != normalized.get("cells"):
        errors.append("notebook cells are not normalized")

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        print(
            f"OK: {path} ({len(normalized['cells'])} cells, structure unchanged)"
        )
        return 0

    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"OK: normalized {path} ({len(normalized['cells'])} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
