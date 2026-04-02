import struct

from hcpbench.protocol import HEADER_SIZE, MAGIC, MsgType, pack_header, unpack_header


def test_header_roundtrip():
    b = pack_header(MsgType.Ping, 42, 0, 1_234_567_890)
    assert len(b) == HEADER_SIZE
    h = unpack_header(b)
    assert h.magic == MAGIC
    assert h.type == int(MsgType.Ping)
    assert h.version == 1
    assert h.seq == 42
    assert h.payload_len == 0
    assert h.ts_ns == 1_234_567_890


def test_cpp_layout_matches_ihhiqq():
    # Must match cpp/include/hcp/protocol.hpp (packed)
    fmt = struct.Struct("<IHHIQQ")
    assert fmt.size == 28
