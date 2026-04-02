# HCP-bench

**HPC-Scale Distributed Compute Benchmark Suite** — measuring **throughput**, **round-trip latency**, and **jitter** on distributed workloads. A **C++ worker** (low overhead) plus a **Python** orchestration layer (YAML scenarios, statistics, JSON reports).


## What this measures

| Mode | What it exercises | Metrics |
|------|-------------------|---------|
| **ping** | TCP request/response (ping/pong) | Mean RTT, p50/p90/p99/p99.9, std-dev (jitter), min/max |
| **throughput** | Bulk echo (send chunk → receive echo) | Gb/s, MiB/s, wall time |

Use these to profile **communication overhead** between nodes, compare **latency tails** under load, and sanity-check **scalability** (same workload across more hosts or processes).

## Quick start (Python worker, no C++ build)

```bash
cd HCP
pip install -e ".[dev]"
python -m hcpbench run examples/benchmark.yaml -o out/report.json
```

The default `examples/benchmark.yaml` uses the pure-Python worker so you can run immediately on Windows, Linux, or macOS.

## Using the C++ worker

1. Configure CMake and build `hcp_worker`:

   ```bash
   cd cpp
   cmake -B build -DCMAKE_BUILD_TYPE=Release
   cmake --build build --config Release
   ```

   On Windows with Visual Studio, prefer `-G "Visual Studio 17 2022" -A x64` (or Ninja if installed).

2. Point the suite at the binary:

   ```yaml
   worker:
     backend: cpp
     exe: cpp/build/Release/hcp_worker.exe    # Windows
     # exe: cpp/build/hcp_worker              # Linux / macOS
   ```

3. Or set `HCP_WORKER` to the full path of `hcp_worker`.

The C++ and Python workers speak the **same 28-byte packed binary header** (`MAGIC`, message type, version, sequence, payload length, timestamp).

## Wire protocol (summary)

- **Hello / HelloAck** — session handshake  
- **Ping / Pong** — client sends `ts_ns` in header; server echoes **Pong** with the same `ts_ns` for RTT  
- **BulkStart / BulkChunk / BulkDone** — throughput mode with echo of each chunk  

All multi-byte fields are **little-endian** on the wire (typical for x86/ARM clusters).

## Comparing C++ vs Python (same machine)

The harness is the same; only the **worker process** changes. Run two reports and compare JSON or the printed summary.

```bash
python -m hcpbench run examples/benchmark.yaml        -o out/report_python.json
python -m hcpbench run examples/benchmark_cpp.yaml      -o out/report_cpp.yaml
```

On Windows you can use `scripts/compare_backends.ps1` after building the C++ binary (it writes both files under `out/`).

**What to expect**

- **Ping**: C++ and Python often look similar on loopback; both are dominated by the OS TCP stack.
- **Throughput**: C++ usually **higher** MiB/s and Gb/s because the Python path spends more time in the interpreter and allocations. Use the same `bytes` / `chunk` in both YAML files for a fair comparison.

## Two machines on the same switch

Use **`examples/two_hosts_same_switch.yaml`** as a template. Workflow:

1. **Receiver** (the node that echoes traffic): open TCP **9000** in the firewall if needed, then start the worker:
   - `hcp_worker --server --bind 0.0.0.0 --port 9000`  
   - or `python -m hcpbench.worker_py --server --bind 0.0.0.0 --port 9000`
2. Edit the YAML: replace `RECEIVER_IP` with that host’s address (e.g. `10.0.0.12`). Use the **same** `port` as on the server.
3. **Sender** (any machine that can route to the receiver—typically another host on the same switch): install the repo, set `worker` to `python` or `cpp` **to match what you started on the receiver**, and run:
   - `python -m hcpbench run examples/two_hosts_same_switch.yaml -o out/cross.json`

The file sets **`external_server: true`** so `hcpbench` does **not** start a server on the sender; it only runs clients toward `targets[].host`.

**Tips**

- For a clean network test, pick a **dedicated** NIC/subnet if you can, and avoid running heavy jobs on both CPUs during the measurement.
- Same-switch latency is often **tens to hundreds of microseconds** RTT for TCP, depending on NIC, offload, and load—much more than loopback.

## Multi-node runs (general)

1. Start **one server** on the receiver node (command above).
2. Point **`targets[].host`** at the receiver IP.
3. Use **`external_server: true`** when the server is not on the machine where you run `hcpbench`.

For automation, wrap SSH/Slurm/Kubernetes around the same commands; the worker stays a small, auditable process.

## Project layout

```
HCP/
  cpp/                 # CMake project → hcp_worker
  python/hcpbench/     # Orchestrator, metrics, protocol, Python worker
  examples/            # Sample benchmark matrix
  tests/               # Pytest (metrics + protocol)
```

## Development

```bash
pytest tests -q
```

## License

MIT — see [LICENSE](LICENSE).
