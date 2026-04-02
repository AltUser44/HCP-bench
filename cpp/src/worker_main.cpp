#include "hcp/net.hpp"
#include "hcp/protocol.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

using namespace hcp;
using hcp::net::Socket;

uint64_t now_ns() {
  using clock = std::chrono::steady_clock;
  return std::chrono::duration_cast<std::chrono::nanoseconds>(clock::now().time_since_epoch())
      .count();
}

bool send_msg(const Socket& s, MsgType type, uint32_t seq, uint64_t ts_ns, const void* payload,
              uint64_t payload_len) {
  Header h{};
  h.encode();
  h.type = static_cast<uint16_t>(type);
  h.seq = seq;
  h.payload_len = payload_len;
  h.ts_ns = ts_ns;
  if (!hcp::net::send_all(s, &h, sizeof(h)))
    return false;
  if (payload_len > 0 && payload)
    return hcp::net::send_all(s, payload, static_cast<size_t>(payload_len));
  return true;
}

bool recv_msg(const Socket& s, Header& h, std::vector<uint8_t>& payload) {
  if (!hcp::net::recv_all(s, &h, sizeof(h)))
    return false;
  if (!h.valid()) {
    std::fprintf(stderr, "hcp_worker: invalid header\n");
    return false;
  }
  payload.resize(static_cast<size_t>(h.payload_len));
  if (h.payload_len > 0) {
    if (!hcp::net::recv_all(s, payload.data(), static_cast<size_t>(h.payload_len)))
      return false;
  }
  return true;
}

int run_server(const std::string& bind_host, uint16_t port) {
  Socket listener{};
  if (!hcp::net::tcp_listen(bind_host, port, listener)) {
    std::fprintf(stderr, "hcp_worker: listen failed on %s:%u\n", bind_host.c_str(), port);
    return 1;
  }
  std::fprintf(stderr, "hcp_worker: listening on %s:%u\n", bind_host.c_str(), port);

  for (;;) {
    Socket client{};
    std::string peer;
    if (!hcp::net::tcp_accept(listener, client, peer)) {
      std::fprintf(stderr, "hcp_worker: accept failed\n");
      continue;
    }
    std::fprintf(stderr, "hcp_worker: accepted %s\n", peer.c_str());

    for (;;) {
      Header h{};
      std::vector<uint8_t> payload;
      if (!recv_msg(client, h, payload)) {
        std::fprintf(stderr, "hcp_worker: peer disconnected\n");
        break;
      }
      auto t = static_cast<MsgType>(h.type);
      if (t == MsgType::Shutdown)
        break;
      if (t == MsgType::Hello) {
        send_msg(client, MsgType::HelloAck, h.seq, now_ns(), nullptr, 0);
        continue;
      }
      if (t == MsgType::Ping) {
        send_msg(client, MsgType::Pong, h.seq, h.ts_ns, nullptr, 0);
        continue;
      }
      if (t == MsgType::BulkStart) {
        send_msg(client, MsgType::HelloAck, h.seq, now_ns(), nullptr, 0);
        continue;
      }
      if (t == MsgType::BulkChunk) {
        send_msg(client, MsgType::BulkChunk, h.seq, now_ns(), payload.data(), payload.size());
        continue;
      }
      if (t == MsgType::BulkDone) {
        send_msg(client, MsgType::BulkDone, h.seq, now_ns(), nullptr, 0);
        continue;
      }
      std::fprintf(stderr, "hcp_worker: unknown msg type %u\n", h.type);
      break;
    }
    hcp::net::close_socket(client);
  }
  hcp::net::close_socket(listener);
  return 0;
}

int run_client_ping(const std::string& host, uint16_t port, uint32_t count, uint32_t warmup) {
  Socket s{};
  if (!hcp::net::tcp_connect(host, port, s)) {
    std::fprintf(stderr, "hcp_worker: connect failed %s:%u\n", host.c_str(), port);
    return 1;
  }
  Header rh{};
  std::vector<uint8_t> rp;
  if (!send_msg(s, MsgType::Hello, 0, now_ns(), nullptr, 0) || !recv_msg(s, rh, rp)) {
    std::fprintf(stderr, "hcp_worker: hello failed\n");
    return 1;
  }

  std::vector<uint64_t> samples;
  samples.reserve(count);

  for (uint32_t i = 0; i < warmup + count; ++i) {
    uint64_t t0 = now_ns();
    if (!send_msg(s, MsgType::Ping, i, t0, nullptr, 0))
      return 1;
    if (!recv_msg(s, rh, rp) || static_cast<MsgType>(rh.type) != MsgType::Pong) {
      std::fprintf(stderr, "hcp_worker: pong failed\n");
      return 1;
    }
    uint64_t t1 = now_ns();
    if (i >= warmup)
      samples.push_back(t1 - t0);
  }

  send_msg(s, MsgType::Shutdown, 0, 0, nullptr, 0);
  hcp::net::close_socket(s);

  uint64_t sum = 0;
  for (uint64_t v : samples)
    sum += v;
  double mean = samples.empty() ? 0.0 : static_cast<double>(sum) / samples.size();

  double var = 0;
  for (uint64_t v : samples) {
    double d = static_cast<double>(v) - mean;
    var += d * d;
  }
  if (!samples.empty())
    var /= samples.size();
  double jitter_ns = std::sqrt(var);

  std::printf(
      "{\"mode\":\"ping\",\"samples\":%zu,\"mean_rtt_ns\":%.3f,\"jitter_ns\":%.3f,\"min_ns\":",
      samples.size(), mean, jitter_ns);
  if (samples.empty()) {
    std::printf("null,\"max_ns\":null,\"raw_ns\":[");
  } else {
    uint64_t mn = samples[0], mx = samples[0];
    for (uint64_t v : samples) {
      mn = std::min(mn, v);
      mx = std::max(mx, v);
    }
    std::printf("%llu,\"max_ns\":%llu,\"raw_ns\":[", static_cast<unsigned long long>(mn),
                static_cast<unsigned long long>(mx));
    for (size_t i = 0; i < samples.size(); ++i) {
      if (i)
        std::printf(",");
      std::printf("%llu", static_cast<unsigned long long>(samples[i]));
    }
  }
  std::printf("]}\n");
  return 0;
}

int run_client_bulk(const std::string& host, uint16_t port, uint64_t total_bytes, uint32_t chunk) {
  Socket s{};
  if (!hcp::net::tcp_connect(host, port, s)) {
    std::fprintf(stderr, "hcp_worker: connect failed %s:%u\n", host.c_str(), port);
    return 1;
  }
  Header rh{};
  std::vector<uint8_t> rp;
  if (!send_msg(s, MsgType::Hello, 0, now_ns(), nullptr, 0) || !recv_msg(s, rh, rp)) {
    std::fprintf(stderr, "hcp_worker: hello failed\n");
    return 1;
  }

  std::vector<uint8_t> buf(chunk);
  for (uint32_t i = 0; i < buf.size(); ++i)
    buf[i] = static_cast<uint8_t>(i & 0xff);

  if (!send_msg(s, MsgType::BulkStart, 0, total_bytes, nullptr, 0)) {
    std::fprintf(stderr, "hcp_worker: bulk start failed\n");
    return 1;
  }
  if (!recv_msg(s, rh, rp)) {
    std::fprintf(stderr, "hcp_worker: bulk start ack failed\n");
    return 1;
  }

  uint64_t sent = 0;
  uint32_t seq = 0;
  uint64_t t0 = now_ns();
  while (sent < total_bytes) {
    uint32_t n = static_cast<uint32_t>(std::min<uint64_t>(chunk, total_bytes - sent));
    buf.resize(n);
    if (!send_msg(s, MsgType::BulkChunk, seq++, 0, buf.data(), n))
      return 1;
    if (!recv_msg(s, rh, rp)) {
      std::fprintf(stderr, "hcp_worker: bulk chunk failed\n");
      return 1;
    }
    if (rp.size() != n) {
      std::fprintf(stderr, "hcp_worker: echo size mismatch\n");
      return 1;
    }
    sent += n;
  }

  if (!send_msg(s, MsgType::BulkDone, 0, 0, nullptr, 0) || !recv_msg(s, rh, rp)) {
    std::fprintf(stderr, "hcp_worker: bulk done failed\n");
    return 1;
  }
  uint64_t t1 = now_ns();
  send_msg(s, MsgType::Shutdown, 0, 0, nullptr, 0);
  hcp::net::close_socket(s);

  double secs = (t1 - t0) / 1e9;
  double gbps = (total_bytes * 8.0) / secs / 1e9;
  double mb_s = total_bytes / secs / (1024.0 * 1024.0);

  std::printf(
      "{\"mode\":\"throughput\",\"bytes\":%llu,\"seconds\":%.9f,\"throughput_gbps\":%.6f,"
      "\"throughput_mib_s\":%.3f}\n",
      static_cast<unsigned long long>(total_bytes), secs, gbps, mb_s);
  return 0;
}

void usage() {
  std::fprintf(stderr,
               "Usage:\n"
               "  hcp_worker --server [--bind HOST] --port PORT\n"
               "  hcp_worker --client --host HOST --port PORT --mode ping [--count N] [--warmup W]\n"
               "  hcp_worker --client --host HOST --port PORT --mode throughput --bytes B [--chunk C]\n");
}

} // namespace

int main(int argc, char** argv) {
  if (!hcp::net::init_network()) {
    std::fprintf(stderr, "hcp_worker: network init failed\n");
    return 1;
  }

  bool server = false;
  bool client = false;
  std::string bind_host = "0.0.0.0";
  std::string host = "127.0.0.1";
  uint16_t port = 9000;
  std::string mode = "ping";
  uint32_t count = 10000;
  uint32_t warmup = 1000;
  uint64_t bytes = 256ull * 1024 * 1024;
  uint32_t chunk = 64 * 1024;

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    auto next = [&]() -> const char* {
      if (i + 1 < argc)
        return argv[++i];
      usage();
      std::exit(1);
    };
    if (a == "--server")
      server = true;
    else if (a == "--client")
      client = true;
    else if (a == "--bind")
      bind_host = next();
    else if (a == "--host")
      host = next();
    else if (a == "--port")
      port = static_cast<uint16_t>(std::atoi(next()));
    else if (a == "--mode")
      mode = next();
    else if (a == "--count")
      count = static_cast<uint32_t>(std::strtoul(next(), nullptr, 10));
    else if (a == "--warmup")
      warmup = static_cast<uint32_t>(std::strtoul(next(), nullptr, 10));
    else if (a == "--bytes")
      bytes = std::strtoull(next(), nullptr, 10);
    else if (a == "--chunk")
      chunk = static_cast<uint32_t>(std::strtoul(next(), nullptr, 10));
    else if (a == "--help" || a == "-h") {
      usage();
      return 0;
    } else {
      usage();
      return 1;
    }
  }

  int rc = 0;
  if (server && !client)
    rc = run_server(bind_host, port);
  else if (client && !server) {
    if (mode == "ping")
      rc = run_client_ping(host, port, count, warmup);
    else if (mode == "throughput")
      rc = run_client_bulk(host, port, bytes, chunk);
    else {
      usage();
      rc = 1;
    }
  } else {
    usage();
    rc = 1;
  }

  hcp::net::shutdown_network();
  return rc;
}
