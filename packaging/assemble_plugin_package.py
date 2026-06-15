"""Assemble the Substance Designer plugin into a zip archive."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Package the Substance Designer MCP plugin")
    parser.add_argument("--plugin-dir", default="plugin", help="Source plugin directory")
    parser.add_argument("--output-dir", default="dist_plugin", help="Output directory")
    parser.add_argument("--name", default="dcc-mcp-substancedesigner-plugin", help="Archive base name")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    plugin_dir = (repo_root / args.plugin_dir).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    archive_path = output_dir / f"{args.name}.zip"

    if not plugin_dir.is_dir():
        raise SystemExit(f"Plugin directory not found: {plugin_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_dir():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, Path("dcc-mcp-substancedesigner") / path.relative_to(plugin_dir))

    shutil.copy2(repo_root / "README.md", output_dir / "README.md")
    print(f"Wrote {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
