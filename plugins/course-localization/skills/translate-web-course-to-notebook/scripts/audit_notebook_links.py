#!/usr/bin/env python3
"""Проверить Markdown-ссылки в Jupyter Notebook и сверить их с реестром."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\((https?://[^)\s]+)\)")
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
AUTOLINK_RE = re.compile(r"<https?://[^>\s]+>")
URL_RE = re.compile(r"https?://[^\s<>)\]]+")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Проверить, что внешние ссылки оформлены Markdown-синтаксисом "
            "и все ожидаемые URL присутствуют в блокноте."
        )
    )
    parser.add_argument("notebook", type=Path, help="Путь к файлу .ipynb")
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        metavar="URL",
        help="Ожидаемый URL; параметр можно повторять",
    )
    parser.add_argument(
        "--expect-file",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help="Текстовый файл с одним ожидаемым URL в строке",
    )
    return parser.parse_args()


def load_expected(args: argparse.Namespace) -> set[str]:
    expected = {url.strip() for url in args.expect if url.strip()}
    for path in args.expect_file:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if value and not value.startswith("#"):
                expected.add(value)
    invalid = sorted(url for url in expected if not re.fullmatch(r"https?://\S+", url))
    if invalid:
        raise ValueError("Некорректные URL в реестре: " + ", ".join(invalid))
    return expected


def markdown_cells(notebook: dict) -> list[tuple[int, str]]:
    result = []
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", "")
        text = "".join(source) if isinstance(source, list) else str(source)
        result.append((index, text))
    return result


def strip_fenced_and_inline_code(text: str) -> str:
    kept: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                in_fence = False
            kept.append("")
            continue
        kept.append("" if in_fence else INLINE_CODE_RE.sub("", line))
    return "\n".join(kept)


def audit(cells: list[tuple[int, str]]) -> tuple[set[str], list[str]]:
    destinations: set[str] = set()
    errors: list[str] = []
    for index, text in cells:
        prose = strip_fenced_and_inline_code(text)
        destinations.update(MARKDOWN_LINK_RE.findall(prose))

        if AUTOLINK_RE.search(prose):
            errors.append(
                f"ячейка {index}: угловая автоссылка должна быть оформлена как [подпись](URL)"
            )

        without_links = MARKDOWN_IMAGE_RE.sub("", MARKDOWN_LINK_RE.sub("", prose))
        for match in URL_RE.finditer(without_links):
            errors.append(f"ячейка {index}: голый URL {match.group(0)}")
    return destinations, errors


def main() -> int:
    args = parse_args()
    try:
        notebook = json.loads(args.notebook.read_text(encoding="utf-8"))
        expected = load_expected(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    destinations, errors = audit(markdown_cells(notebook))
    missing = sorted(expected - destinations)
    if missing:
        errors.append("потеряны ожидаемые URL: " + ", ".join(missing))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"OK: {args.notebook} "
        f"({len(destinations)} уникальных внешних Markdown-ссылок, "
        f"{len(expected)} ожидаемых)"
    )
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
