"""Binary wire protocol matching `cpp/include/hcp/protocol.hpp` (little-endian)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

# magic(u32) type(u16) version(u16) seq(u32) payload_len(u64) ts_ns(u64) — 28 bytes, packed
HEADER_STRUCT = struct.Struct("<IHHIQQ")
HEADER_SIZE = HEADER_STRUCT.size

MAGIC = 0x31435048


class MsgType(IntEnum):
    Hello = 1
    HelloAck = 2
    Ping = 3
    Pong = 4
    BulkStart = 5
    BulkChunk = 6
    BulkDone = 7
    Shutdown = 8


@dataclass(slots=True)
class Header:
    magic: int
    type: int
    version: int
    seq: int
    payload_len: int
    ts_ns: int

    def valid(self) -> bool:
        return self.magic == MAGIC and self.version == 1


def pack_header(msg_type: MsgType, seq: int, payload_len: int, ts_ns: int) -> bytes:
    return HEADER_STRUCT.pack(MAGIC, int(msg_type), 1, seq, payload_len, ts_ns)


def unpack_header(data: bytes) -> Header:
    if len(data) != HEADER_SIZE:
        raise ValueError("header size mismatch")
    m, t, ver, seq, plen, ts = HEADER_STRUCT.unpack(data)
    return Header(magic=m, type=t, version=ver, seq=seq, payload_len=plen, ts_ns=ts)
