#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace hcp::net {

struct Socket {
  int fd{-1};
#ifdef _WIN32
  using sock_t = uintptr_t;
#else
  using sock_t = int;
#endif
};

bool init_network();
void shutdown_network();

bool tcp_listen(const std::string& host, uint16_t port, Socket& out);
bool tcp_accept(const Socket& listener, Socket& client, std::string& peer_host);
bool tcp_connect(const std::string& host, uint16_t port, Socket& out);

void close_socket(Socket& s);

bool send_all(const Socket& s, const void* data, size_t len);
bool recv_all(const Socket& s, void* data, size_t len);

} // namespace hcp::net
