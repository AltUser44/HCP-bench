"""Launch workers, run benchmark scenarios, and assemble structured reports."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from hcpbench.metrics import summarize_ns

Backend = Literal["cpp", "python"]


@dataclass(slots=True)
class WorkerPaths:
    backend: Backend
    exe: str | None
    python_module: str = "hcpbench.worker_py"


def _resolve_worker(cfg: dict[str, Any]) -> WorkerPaths:
    w = cfg.get("worker") or {}
    backend = str(w.get("backend", "python")).lower()
    if backend not in ("cpp", "python"):
        backend = "python"
    exe = w.get("exe") or os.environ.get("HCP_WORKER")
    return WorkerPaths(backend=backend, exe=exe)


def _wait_tcp(host: str, port: int, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last = e
            time.sleep(0.05)
    raise TimeoutError(f"TCP {host}:{port} not reachable: {last}")


def _server_cmd(paths: WorkerPaths, bind: str, port: int) -> list[str]:
    if paths.backend == "cpp":
        if not paths.exe:
            raise RuntimeError(
                "worker.backend is 'cpp' but no executable: set worker.exe or HCP_WORKER"
            )
        return [paths.exe, "--server", "--bind", bind, "--port", str(port)]
    return [sys.executable, "-m", paths.python_module, "--server", "--bind", bind, "--port", str(port)]


def _client_cmd(
    paths: WorkerPaths,
    host: str,
    port: int,
    mode: str,
    extra: dict[str, Any],
) -> list[str]:
    if paths.backend == "cpp":
        if not paths.exe:
            raise RuntimeError("worker.backend is 'cpp' but no executable path")
        cmd = [
            paths.exe,
            "--client",
            "--host",
            host,
            "--port",
            str(port),
            "--mode",
            mode,
        ]
        if mode == "ping":
            cmd += [
                "--count",
                str(extra.get("count", 10_000)),
                "--warmup",
                str(extra.get("warmup", 1000)),
            ]
        else:
            cmd += [
                "--bytes",
                str(extra.get("bytes", 256 * 1024 * 1024)),
                "--chunk",
                str(extra.get("chunk", 65536)),
            ]
        return cmd
    cmd = [
        sys.executable,
        "-m",
        paths.python_module,
        "--client",
        "--host",
        host,
        "--port",
        str(port),
        "--mode",
        mode,
    ]
    if mode == "ping":
        cmd += [
            "--count",
            str(extra.get("count", 10_000)),
            "--warmup",
            str(extra.get("warmup", 1000)),
        ]
    else:
        cmd += [
            "--bytes",
            str(extra.get("bytes", 256 * 1024 * 1024)),
            "--chunk",
            str(extra.get("chunk", 65536)),
        ]
    return cmd


def _parse_client_json(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise ValueError("no JSON object in client output")


def run_scenario(
    paths: WorkerPaths,
    bind_host: str,
    port: int,
    target: dict[str, Any],
    *,
    start_server: bool,
    connect_host: str = "127.0.0.1",
) -> dict[str, Any]:
    name = target.get("name", "scenario")
    host = str(target.get("host", "127.0.0.1"))
    mode = str(target.get("mode", "ping"))
    extra = {k: v for k, v in target.items() if k not in ("name", "host", "mode")}

    proc: subprocess.Popen | None = None
    try:
        if start_server:
            cmd = _server_cmd(paths, bind_host, port)
            kwargs: dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "text": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            proc = subprocess.Popen(cmd, **kwargs)
            _wait_tcp(connect_host, port, timeout_s=float(target.get("server_ready_s", 15.0)))
            if proc.poll() is not None:
                raise RuntimeError("server exited before accepting connections")

        ccmd = _client_cmd(paths, host, port, mode, extra)
        cp = subprocess.run(ccmd, capture_output=True, text=True, timeout=600)
        out = cp.stdout + "\n" + (cp.stderr or "")
        if cp.returncode != 0:
            return {
                "name": name,
                "mode": mode,
                "error": f"exit {cp.returncode}: {out[-2000:]}",
            }

        data = _parse_client_json(cp.stdout)
        if mode == "ping":
            raw = data.get("raw_ns") or []
            stats = summarize_ns([float(x) for x in raw])
            return {
                "name": name,
                "mode": "ping",
                "host": host,
                "stats": stats,
                "mean_rtt_ns": data.get("mean_rtt_ns"),
                "jitter_ns": data.get("jitter_ns"),
            }
        return {
            "name": name,
            "mode": "throughput",
            "host": host,
            "bytes": data.get("bytes"),
            "seconds": data.get("seconds"),
            "throughput_gbps": data.get("throughput_gbps"),
            "throughput_mib_s": data.get("throughput_mib_s"),
        }
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text)


def run_suite(config_path: Path) -> dict[str, Any]:
    cfg = load_config(config_path)
    paths = _resolve_worker(cfg)
    bind = str((cfg.get("bind") or {}).get("host", "0.0.0.0"))
    port = int((cfg.get("bind") or {}).get("port", 9000))
    connect_host = str(cfg.get("connect_host") or "127.0.0.1")
    targets = cfg.get("targets") or []
    meta = {
        "suite": cfg.get("suite", "hcpbench"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path.resolve()),
        "worker": {"backend": paths.backend, "exe": paths.exe},
    }

    external = bool(cfg.get("external_server", False))
    runs: list[dict[str, Any]] = []
    for t in targets:
        # external_server: true → do not spawn a local worker (you started one on another host)
        if "start_server" in t:
            start_srv = bool(t["start_server"])
        else:
            start_srv = not external
        run = run_scenario(paths, bind, port, t, start_server=start_srv, connect_host=connect_host)
        runs.append(run)

    return {"meta": meta, "runs": runs}
