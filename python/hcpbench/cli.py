"""Command-line entry for the HCP benchmark suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hcpbench import __version__
from hcpbench.orchestrator import run_suite
from hcpbench.report import format_summary, write_json


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hcpbench", description="HPC-scale distributed compute benchmarks")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run scenarios from a YAML config")
    run_p.add_argument("config", type=Path, help="Path to benchmark YAML")
    run_p.add_argument("-o", "--output", type=Path, help="Write JSON report to this path")
    run_p.add_argument("-q", "--quiet", action="store_true", help="Suppress summary on stdout")

    return 0 if _dispatch(p.parse_args(argv)) else 1


def _dispatch(args: argparse.Namespace) -> bool:
    if args.cmd == "run":
        report = run_suite(args.config)
        if args.output:
            write_json(args.output, report)
        if not args.quiet:
            sys.stdout.write(format_summary(report))
        return all("error" not in r for r in report.get("runs", []))
    return False


if __name__ == "__main__":
    raise SystemExit(main())
