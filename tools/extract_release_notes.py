"""Extract release notes for a tag from CHANGELOG.md."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract one release section from CHANGELOG.md")
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.1.1")
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--output", type=Path, default=Path("release-notes.md"))
    args = parser.parse_args(argv)

    version = args.tag.removeprefix("v")
    notes = extract_notes(args.changelog, version)
    args.output.write_text(notes, encoding="utf-8")
    return 0


def extract_notes(changelog_path: Path, version: str) -> str:
    if not changelog_path.is_file():
        return f"Release {version}\n"

    text = changelog_path.read_text(encoding="utf-8")
    heading = re.compile(rf"^##\s+\[?v?{re.escape(version)}\]?.*$", re.MULTILINE)
    match = heading.search(text)
    if match is None:
        return f"Release {version}\n"

    next_heading = re.search(r"^##\s+", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.start() : end].strip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
