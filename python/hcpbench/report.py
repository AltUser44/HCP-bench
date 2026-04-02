"""JSON report aggregation and optional console summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path | str, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def format_summary(report: dict[str, Any]) -> str:
    lines: list[str] = []
    meta = report.get("meta", {})
    lines.append(f"HCP Benchmark Report - {meta.get('suite', 'hcpbench')}")
    lines.append(f"  generated: {meta.get('timestamp', '')}")
    lines.append("")
    for run in report.get("runs", []):
        name = run.get("name", "run")
        mode = run.get("mode", "")
        lines.append(f"## {name} ({mode})")
        if mode == "ping":
            s = run.get("stats", {})
            lines.append(
                f"  samples: {int(s.get('count', 0))}  "
                f"mean RTT: {s.get('mean_ns', 0) / 1e6:.4f} ms  "
                f"p99: {s.get('p99_ns', 0) / 1e6:.4f} ms  "
                f"jitter (std): {s.get('jitter_ns', 0) / 1e6:.4f} ms"
            )
        elif mode == "throughput":
            lines.append(
                f"  {run.get('throughput_gbps', 0):.3f} Gb/s  "
                f"{run.get('throughput_mib_s', 0):.1f} MiB/s  "
                f"bytes: {run.get('bytes', 0)}"
            )
        err = run.get("error")
        if err:
            lines.append(f"  ERROR: {err}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
