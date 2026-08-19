#!/usr/bin/env python3
"""Normalize Russian GitHub repository visibility terms in Jupyter notebooks."""

from __future__ import annotations

import argparse
import codecs
import json
import re
import sys
from pathlib import Path


ADJECTIVES = {
    "public": {
        "общедоступный": "публичный",
        "общедоступного": "публичного",
        "общедоступному": "публичному",
        "общедоступным": "публичным",
        "общедоступном": "публичном",
        "общедоступные": "публичные",
        "общедоступных": "публичных",
        "общедоступными": "публичными",
        "публичный": "публичный",
        "публичного": "публичного",
        "публичному": "публичному",
        "публичным": "публичным",
        "публичном": "публичном",
        "публичные": "публичные",
        "публичных": "публичных",
        "публичными": "публичными",
    },
    "private": {
        "закрытый": "частный",
        "закрытого": "частного",
        "закрытому": "частному",
        "закрытым": "частным",
        "закрытом": "частном",
        "закрытые": "частные",
        "закрытых": "частных",
        "закрытыми": "частными",
        "частный": "частный",
        "частного": "частного",
        "частному": "частному",
        "частным": "частным",
        "частном": "частном",
        "частные": "частные",
        "частных": "частных",
        "частными": "частными",
    },
    "internal": {
        "внутренний": "внутренний",
        "внутреннего": "внутреннего",
        "внутреннему": "внутреннему",
        "внутренним": "внутренним",
        "внутреннем": "внутреннем",
        "внутренние": "внутренние",
        "внутренних": "внутренних",
        "внутренними": "внутренними",
    },
}

ADJECTIVE_INDEX = {
    form: (visibility, normalized)
    for visibility, forms in ADJECTIVES.items()
    for form, normalized in forms.items()
}
ADJECTIVE_PATTERN = "|".join(
    sorted((re.escape(value) for value in ADJECTIVE_INDEX), key=len, reverse=True)
)
REPOSITORY_PATTERN = r"репозитор(?:ий|ия|ию|ием|ии|иев|иям|иями|иях)"
PHRASE_RE = re.compile(
    rf"\b(?P<first>{ADJECTIVE_PATTERN})"
    rf"(?:\s+(?P<conjunction>и|или)\s+(?P<second>{ADJECTIVE_PATTERN}))?"
    rf"\s+(?P<noun>{REPOSITORY_PATTERN})\b"
    rf"(?![-–—]|\s*\((?:public|private|internal) repositor(?:y|ies)\))",
    re.IGNORECASE,
)

TEMPLATE_RE = re.compile(
    r"\b(?:общедоступный|публичный)\s+(?:репозиторий-шаблон|шаблонный репозиторий)\b"
    r"(?!\s*\(public template repository\))",
    re.IGNORECASE,
)

REVERSE_PRIVATE_RE = re.compile(
    r"\bЕсли репозиторий (?:закрытый|частный),",
    re.IGNORECASE,
)

VISIBILITY_LIST_RE = re.compile(
    r"\*\*(?:общедоступный|публичный)\*\*,\s*"
    r"\*\*(?:закрытый|частный)\*\*\s+или\s+"
    r"\*\*внутренний\*\*",
    re.IGNORECASE,
)

VISIBILITY_LABELS = (
    (re.compile(r"\*\*(?:Общедоступный|Публичный)(?:\s*\(Public\))?:\*\*", re.IGNORECASE),
     "**Публичный репозиторий (Public repository):**"),
    (re.compile(r"\*\*(?:Закрытый|Частный)(?:\s*\(Private\))?:\*\*", re.IGNORECASE),
     "**Частный репозиторий (Private repository):**"),
    (re.compile(r"\*\*Внутренний(?:\s*\(Internal\))?:\*\*", re.IGNORECASE),
     "**Внутренний репозиторий (Internal repository):**"),
)


def preserve_initial_case(source: str, replacement: str) -> str:
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def is_plural(noun: str, adjective: str) -> bool:
    noun_lower = noun.lower()
    adjective_lower = adjective.lower()
    if noun_lower == "репозитории":
        return adjective_lower.endswith(("ые", "ие"))
    return noun_lower in {"репозиториев", "репозиториям", "репозиториями", "репозиториях"}


def normalize_part(adjective: str, noun: str) -> str:
    visibility, normalized = ADJECTIVE_INDEX[adjective.lower()]
    normalized = preserve_initial_case(adjective, normalized)
    plural = is_plural(noun, adjective)
    english = f"{visibility} {'repositories' if plural else 'repository'}"
    english = preserve_initial_case(adjective, english)
    return f"{normalized} {noun} ({english})"


def replace_phrase(match: re.Match[str]) -> str:
    first = normalize_part(match.group("first"), match.group("noun"))
    second_adjective = match.group("second")
    if not second_adjective:
        return first
    second = normalize_part(second_adjective, match.group("noun"))
    return f"{first} {match.group('conjunction')} {second}"


def normalize_text(text: str) -> tuple[str, int]:
    changes = 0

    def substitute(pattern: re.Pattern[str], replacement) -> None:
        nonlocal text, changes
        text, count = pattern.subn(replacement, text)
        changes += count

    substitute(
        TEMPLATE_RE,
        lambda match: preserve_initial_case(
            match.group(0), "публичный репозиторий-шаблон (public template repository)"
        ),
    )
    substitute(
        VISIBILITY_LIST_RE,
        "**публичный репозиторий (public repository)**, "
        "**частный репозиторий (private repository)** или "
        "**внутренний репозиторий (internal repository)**",
    )
    for pattern, replacement in VISIBILITY_LABELS:
        substitute(pattern, replacement)
    substitute(
        REVERSE_PRIVATE_RE,
        lambda match: preserve_initial_case(
            match.group(0), "если это частный репозиторий (private repository),"
        ),
    )
    substitute(PHRASE_RE, replace_phrase)
    return text, changes


def notebook_paths(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".ipynb" else []
    if target.is_dir():
        return sorted(target.rglob("*.ipynb"))
    return []


def json_value_span(text: str, property_name: str) -> tuple[int, int]:
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        raise ValueError("expected a JSON object")
    index += 1

    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            raise ValueError("unterminated JSON object")
        if text[index] == "}":
            break
        key, index = decoder.raw_decode(text, index)
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] != ":":
            raise ValueError("expected a JSON object property")
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
        value_start = index
        _, index = decoder.raw_decode(text, index)
        if key == property_name:
            return value_start, index
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] == "}":
            break
        if text[index] != ",":
            raise ValueError("expected a comma between JSON properties")
        index += 1
    raise ValueError(f"JSON property not found: {property_name}")


def json_array_items_span(text: str) -> list[tuple[int, int, object]]:
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "[":
        raise ValueError("expected a JSON array")
    index += 1
    items: list[tuple[int, int, object]] = []
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            raise ValueError("unterminated JSON array")
        if text[index] == "]":
            return items
        value_start = index
        value, index = decoder.raw_decode(text, index)
        items.append((value_start, index, value))
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] == "]":
            continue
        if text[index] != ",":
            raise ValueError("expected a comma between JSON array items")
        index += 1


def markdown_source_replacements(text: str) -> list[tuple[int, int, str, int]]:
    cells_start, cells_end = json_value_span(text, "cells")
    replacements: list[tuple[int, int, str, int]] = []
    for cell_start, cell_end, cell in json_array_items_span(text[cells_start:cells_end]):
        if not isinstance(cell, dict) or cell.get("cell_type") != "markdown":
            continue
        cell_text = text[cells_start + cell_start : cells_start + cell_end]
        try:
            source_start, source_end = json_value_span(cell_text, "source")
        except ValueError:
            continue
        source = cell.get("source", [])
        if isinstance(source, list):
            normalized_source: object = [normalize_text(str(line))[0] for line in source]
        else:
            normalized_source = normalize_text(str(source))[0]
        if normalized_source == source:
            continue
        changes = sum(
            normalize_text(str(line))[1] for line in source
        ) if isinstance(source, list) else normalize_text(str(source))[1]
        replacements.append(
            (
                cells_start + cell_start + source_start,
                cells_start + cell_start + source_end,
                json.dumps(normalized_source, ensure_ascii=False),
                changes,
            )
        )
    return replacements


def process_notebook(path: Path, check: bool) -> tuple[int, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    payload = raw[len(codecs.BOM_UTF8):] if has_bom else raw
    text = payload.decode("utf-8")
    json.loads(text)
    replacements = markdown_source_replacements(text)
    changes = sum(item[3] for item in replacements)
    if replacements and not check:
        normalized = text
        for start, end, replacement, _ in reversed(replacements):
            normalized = normalized[:start] + replacement + normalized[end:]
        output = normalized.encode("utf-8")
        if has_bom:
            output = codecs.BOM_UTF8 + output
        path.write_bytes(output)
    return changes, bool(changes)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize Public, Private, and Internal repository terminology."
    )
    parser.add_argument("target", help="Notebook file or directory to scan recursively")
    parser.add_argument(
        "--check", action="store_true", help="Report noncompliant notebooks without changing them"
    )
    args = parser.parse_args()

    target = Path(args.target)
    paths = notebook_paths(target)
    if not paths:
        print(f"ERROR: no .ipynb files found at {target}", file=sys.stderr)
        return 2

    changed_files: list[tuple[Path, int]] = []
    for path in paths:
        try:
            changes, changed = process_notebook(path, args.check)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            print(f"ERROR: {path}: {error}", file=sys.stderr)
            return 2
        if changed:
            changed_files.append((path, changes))

    total = sum(changes for _, changes in changed_files)
    mode = "would change" if args.check else "changed"
    for path, changes in changed_files:
        print(f"{mode}: {path} ({changes} replacements)")

    if args.check and changed_files:
        print(
            f"FAIL: {len(changed_files)} notebook(s) require {total} replacement(s)",
            file=sys.stderr,
        )
        return 1

    print(f"OK: scanned {len(paths)} notebook(s); {mode} {total} occurrence(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
