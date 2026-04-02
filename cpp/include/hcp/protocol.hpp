#pragma once

#include <cstdint>
#include <cstring>

namespace hcp {

inline constexpr uint32_t kMagic = 0x31435048u; // "HCP1" (LE wire order)

enum class MsgType : uint16_t {
  Hello = 1,
  HelloAck = 2,
  Ping = 3,
  Pong = 4,
  BulkStart = 5,
  BulkChunk = 6,
  BulkDone = 7,
  Shutdown = 8,
};

#pragma pack(push, 1)
struct Header {
  uint32_t magic;
  uint16_t type;
  uint16_t version;
  uint32_t seq;
  uint64_t payload_len;
  uint64_t ts_ns;

  void encode() {
    magic = kMagic;
    version = 1;
  }

  bool valid() const { return magic == kMagic && version == 1; }
};
#pragma pack(pop)

static_assert(sizeof(Header) == 28, "packed header size");

inline void host_to_net_header(Header& h) {
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
  (void)h;
#else
  // little-endian host: swap to network for multi-byte fields if we used ntohl
  // We keep native LE on wire for simplicity across same-arch clusters; document this.
  (void)h;
#endif
}

} // namespace hcp
