"""Pure-Python HCP worker (server + client) — same protocol as the C++ `hcp_worker`."""

from __future__ import annotations

import json
import socket
import time
from typing import Any

from hcpbench.protocol import HEADER_SIZE, MsgType, pack_header, unpack_header


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf.extend(chunk)
    return bytes(buf)


def _send_exact(conn: socket.socket, data: bytes) -> None:
    off = 0
    while off < len(data):
        n = conn.send(data[off:])
        if n <= 0:
            raise ConnectionError("send failed")
        off += n


def _read_msg(conn: socket.socket) -> tuple[MsgType, int, int, int, bytes]:
    raw = _recv_exact(conn, HEADER_SIZE)
    h = unpack_header(raw)
    if not h.valid():
        raise ValueError("bad magic/version")
    payload = b""
    if h.payload_len:
        payload = _recv_exact(conn, h.payload_len)
    return MsgType(h.type), h.seq, h.payload_len, h.ts_ns, payload


def _write_msg(
    conn: socket.socket, typ: MsgType, seq: int, ts_ns: int, payload: bytes = b""
) -> None:
    head = pack_header(typ, seq, len(payload), ts_ns)
    _send_exact(conn, head + payload)


def serve(bind_host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((bind_host, port))
        s.listen()
        while True:
            conn, _addr = s.accept()
            with conn:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                while True:
                    try:
                        t, seq, _plen, ts_ns, payload = _read_msg(conn)
                    except (ConnectionError, ValueError):
                        break
                    if t == MsgType.Shutdown:
                        break
                    if t == MsgType.Hello:
                        _write_msg(conn, MsgType.HelloAck, seq, time.time_ns())
                    elif t == MsgType.Ping:
                        _write_msg(conn, MsgType.Pong, seq, ts_ns)
                    elif t == MsgType.BulkStart:
                        _write_msg(conn, MsgType.HelloAck, seq, time.time_ns())
                    elif t == MsgType.BulkChunk:
                        _write_msg(conn, MsgType.BulkChunk, seq, time.time_ns(), payload)
                    elif t == MsgType.BulkDone:
                        _write_msg(conn, MsgType.BulkDone, seq, time.time_ns())
                    else:
                        break


def client_ping(host: str, port: int, count: int, warmup: int) -> dict[str, Any]:
    samples: list[int] = []
    with socket.create_connection((host, port), timeout=30) as conn:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _write_msg(conn, MsgType.Hello, 0, time.time_ns())
        _read_msg(conn)

        for i in range(warmup + count):
            t0 = time.time_ns()
            _write_msg(conn, MsgType.Ping, i, t0)
            t, _seq, _pl, _ts, _ = _read_msg(conn)
            if t != MsgType.Pong:
                raise RuntimeError("expected PONG")
            t1 = time.time_ns()
            if i >= warmup:
                samples.append(t1 - t0)
        _write_msg(conn, MsgType.Shutdown, 0, 0)

    import statistics

    if not samples:
        return {"mode": "ping", "samples": 0, "mean_rtt_ns": 0.0, "jitter_ns": 0.0}
    mean = statistics.mean(samples)
    jitter = statistics.pstdev(samples) if len(samples) > 1 else 0.0
    return {
        "mode": "ping",
        "samples": len(samples),
        "mean_rtt_ns": mean,
        "jitter_ns": jitter,
        "min_ns": min(samples),
        "max_ns": max(samples),
        "raw_ns": samples,
    }


def client_throughput(host: str, port: int, total_bytes: int, chunk: int) -> dict[str, Any]:
    buf = bytes((i % 256) for i in range(chunk))
    with socket.create_connection((host, port), timeout=300) as conn:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _write_msg(conn, MsgType.Hello, 0, time.time_ns())
        _read_msg(conn)
        _write_msg(conn, MsgType.BulkStart, 0, total_bytes)
        _read_msg(conn)

        sent = 0
        seq = 0
        t0 = time.perf_counter_ns()
        while sent < total_bytes:
            n = min(chunk, total_bytes - sent)
            piece = buf[:n]
            _write_msg(conn, MsgType.BulkChunk, seq, 0, piece)
            _t, _s, _p, _ts, echo = _read_msg(conn)
            if len(echo) != n:
                raise RuntimeError("echo size mismatch")
            sent += n
            seq += 1
        _write_msg(conn, MsgType.BulkDone, 0, 0)
        _read_msg(conn)
        t1 = time.perf_counter_ns()

    secs = (t1 - t0) / 1e9
    gbps = (total_bytes * 8.0) / secs / 1e9 if secs > 0 else 0.0
    mib_s = total_bytes / secs / (1024.0 * 1024.0) if secs > 0 else 0.0
    return {
        "mode": "throughput",
        "bytes": total_bytes,
        "seconds": secs,
        "throughput_gbps": gbps,
        "throughput_mib_s": mib_s,
    }


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="HCP Python worker")
    p.add_argument("--server", action="store_true")
    p.add_argument("--client", action="store_true")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--mode", default="ping", choices=("ping", "throughput"))
    p.add_argument("--count", type=int, default=10_000)
    p.add_argument("--warmup", type=int, default=1000)
    p.add_argument("--bytes", type=int, default=256 * 1024 * 1024)
    p.add_argument("--chunk", type=int, default=64 * 1024)
    args = p.parse_args()

    if args.server:
        serve(args.bind, args.port)
        return
    if args.client:
        if args.mode == "ping":
            out = client_ping(args.host, args.port, args.count, args.warmup)
        else:
            out = client_throughput(args.host, args.port, args.bytes, args.chunk)
        print(json.dumps(out))
        return
    p.print_help()


if __name__ == "__main__":
    main()
