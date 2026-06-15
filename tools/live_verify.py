"""Run live Substance Designer bridge verification."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence

Runner = Callable[..., subprocess.CompletedProcess[object]]


def main(argv: Sequence[str] | None = None, runner: Runner = subprocess.run) -> int:
    parser = argparse.ArgumentParser(description="Run live Substance Designer MCP verification")
    parser.add_argument("--host", default="127.0.0.1", help="Substance Designer bridge host")
    parser.add_argument("--port", default="9881", help="Substance Designer bridge port")
    parser.add_argument(
        "--mutation",
        action="store_true",
        help="Also run mutation tests that create disposable packages and graphs",
    )
    parser.add_argument(
        "--pytest-args",
        default="-v",
        help="Additional pytest arguments for live test runs",
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env["DCC_MCP_SUBSTANCEDESIGNER_HOST"] = args.host
    env["DCC_MCP_SUBSTANCEDESIGNER_PORT"] = str(args.port)

    bridge_command = [
        sys.executable,
        "-m",
        "dcc_mcp_substancedesigner",
        "--check-bridge",
        "--sd-host",
        args.host,
        "--sd-port",
        str(args.port),
    ]
    if _run_step("bridge readiness", bridge_command, env, runner) != 0:
        return 1

    live_env = env | {"DCC_MCP_SUBSTANCEDESIGNER_LIVE": "1"}
    integration_command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_live_integration.py",
        "-m",
        "integration",
        *_split_pytest_args(args.pytest_args),
    ]
    if _run_step("read-only live integration", integration_command, live_env, runner) != 0:
        return 1

    if args.mutation:
        mutation_command = [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_live_mutation.py",
            "-m",
            "integration",
            *_split_pytest_args(args.pytest_args),
        ]
        if _run_step("mutation live integration", mutation_command, live_env, runner) != 0:
            return 1

    return 0


def _run_step(name: str, command: Sequence[str], env: dict[str, str], runner: Runner) -> int:
    print(f"==> {name}")
    print(" ".join(command))
    completed = runner(command, env=env)
    return int(completed.returncode)


def _split_pytest_args(value: str) -> list[str]:
    return shlex.split(value)


if __name__ == "__main__":
    raise SystemExit(main())
