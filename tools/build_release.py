"""Build release artifacts for CI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build wheel, sdist, and Substance Designer plugin ZIP")
    parser.add_argument("--dist-dir", default="dist", help="Python package artifact directory")
    parser.add_argument("--plugin-output-dir", default="dist_plugin", help="Plugin artifact directory")
    parser.add_argument("--no-clean", action="store_true", help="Keep existing artifact directories")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / args.dist_dir
    plugin_output_dir = repo_root / args.plugin_output_dir

    if not args.no_clean:
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(plugin_output_dir, ignore_errors=True)

    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "packaging/assemble_plugin_package.py",
            "--output-dir",
            str(plugin_output_dir),
        ],
        cwd=repo_root,
        check=True,
    )

    artifacts = (
        sorted(dist_dir.glob("*.whl")) + sorted(dist_dir.glob("*.tar.gz")) + sorted(plugin_output_dir.glob("*.zip"))
    )
    if not artifacts:
        raise SystemExit("No release artifacts were produced.")

    print("Release artifacts:")
    for artifact in artifacts:
        try:
            display_path = artifact.relative_to(repo_root)
        except ValueError:
            display_path = artifact
        print(f"- {display_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
