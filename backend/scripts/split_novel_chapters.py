"""
Split a long novel txt file into chapter records.

This script is the first step of the novel-style training data pipeline:
raw txt -> cleaned text -> chapter records.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path


COMMON_ENCODINGS = [
    "utf-8",
    "utf-8-sig",
    "gb18030",
    "gbk",
    "big5",
]


CN_NUM = r"[0-9一二三四五六七八九十百千零两〇]+"
VOLUME_ONLY_RE = re.compile(rf"^\s*(第{CN_NUM}[卷集部篇册季].*)$")
CHAPTER_ONLY_RE = re.compile(
    rf"^\s*(第{CN_NUM}章.*|番外.*|序章.*|终章.*|后记.*|楔子.*|尾声.*|引子.*)$"
)
COMBINED_HEADING_RE = re.compile(
    rf"^\s*(第{CN_NUM}[卷集部篇册季][^\n]*?)\s+"
    rf"(第{CN_NUM}章.*|番外.*|序章.*|终章.*|后记.*|楔子.*|尾声.*|引子.*)$"
)


@dataclass
class ChapterRecord:
    chapter_index: int
    chapter_id: str
    volume_title: str
    chapter_title: str
    text: str
    char_count: int
    paragraph_count: int


def detect_and_read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    errors: list[str] = []

    for encoding in COMMON_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")

    raise UnicodeDecodeError(
        "unknown",
        raw,
        0,
        1,
        "Failed to decode file with common encodings: " + "; ".join(errors),
    )


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\ufeff", "")
    text = text.replace("\u3000", "　")
    text = text.replace("\x00", "")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def clean_title_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def chapter_slug(index: int) -> str:
    return f"chapter_{index:04d}"


def normalize_chapter_body(lines: list[str]) -> str:
    normalized_lines: list[str] = []
    previous_was_blank = True

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            if not previous_was_blank:
                normalized_lines.append("")
            previous_was_blank = True
            continue

        line = re.sub(r"[ \t]+$", "", line)

        # Chinese novels often use full-width indentation instead of blank lines.
        # Insert a blank line before a new indented paragraph to preserve paragraph structure.
        if line.startswith("　　") and normalized_lines and normalized_lines[-1] != "":
            normalized_lines.append("")

        normalized_lines.append(line)
        previous_was_blank = False

    body = "\n".join(normalized_lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body


def parse_heading_line(line: str) -> tuple[str | None, str | None]:
    cleaned = clean_title_line(line)

    combined_match = COMBINED_HEADING_RE.match(cleaned)
    if combined_match:
        volume_title = combined_match.group(1).strip()
        chapter_title = combined_match.group(2).strip()
        return volume_title, chapter_title

    volume_match = VOLUME_ONLY_RE.match(cleaned)
    if volume_match:
        return volume_match.group(1).strip(), None

    chapter_match = CHAPTER_ONLY_RE.match(cleaned)
    if chapter_match:
        return None, chapter_match.group(1).strip()

    return None, None


def split_into_chapters(text: str) -> list[ChapterRecord]:
    lines = text.splitlines()
    current_volume = ""
    current_title = ""
    current_body: list[str] = []
    records: list[ChapterRecord] = []
    chapter_index = 0

    def flush_current() -> None:
        nonlocal chapter_index, current_title, current_body
        body = normalize_chapter_body(current_body)
        if not current_title or not body:
            current_body = []
            return

        chapter_index += 1
        paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
        records.append(
            ChapterRecord(
                chapter_index=chapter_index,
                chapter_id=chapter_slug(chapter_index),
                volume_title=current_volume,
                chapter_title=current_title,
                text=body,
                char_count=len(body),
                paragraph_count=len(paragraphs),
            )
        )
        current_body = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            current_body.append("")
            continue

        volume_title, chapter_title = parse_heading_line(line)
        if volume_title and chapter_title:
            flush_current()
            current_volume = volume_title
            current_title = chapter_title
            continue

        if volume_title:
            current_volume = volume_title
            continue

        if chapter_title:
            flush_current()
            current_title = chapter_title
            continue

        current_body.append(raw_line.rstrip())

    flush_current()
    return records


def write_outputs(records: list[ChapterRecord], input_path: Path, output_dir: Path, encoding: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    chapters_dir = output_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "source_file": str(input_path),
        "decoded_with": encoding,
        "chapter_count": len(records),
        "chapters": [asdict(record) for record in records],
    }

    (output_dir / "chapters.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for record in records:
        safe_title = re.sub(r'[\\\\/:*?"<>|]+', "_", record.chapter_title)
        file_name = f"{record.chapter_id}_{safe_title}.txt"
        (chapters_dir / file_name).write_text(record.text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a novel txt file into chapters.")
    parser.add_argument("input_file", help="Path to the novel txt file.")
    parser.add_argument(
        "--output-dir",
        help="Output directory. Defaults to <input_stem>_chapters next to the input file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else input_path.with_name(f"{input_path.stem}_chapters")
    )

    text, encoding = detect_and_read_text(input_path)
    text = normalize_text(text)
    records = split_into_chapters(text)
    write_outputs(records, input_path, output_dir, encoding)

    print(f"Input: {input_path}")
    print(f"Decoded with: {encoding}")
    print(f"Chapters: {len(records)}")
    print(f"Output: {output_dir}")
    if records:
        print("First chapters:")
        for record in records[:5]:
            print(
                f"  - {record.chapter_id} | {record.volume_title or '-'} | "
                f"{record.chapter_title} | {record.char_count} chars"
            )


if __name__ == "__main__":
    main()
