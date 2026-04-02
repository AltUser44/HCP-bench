#include "hcp/net.hpp"

#include <cstring>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
using socklen_t = int;
#else
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace hcp::net {

#ifdef _WIN32
static bool wsa_inited = false;
#endif

bool init_network() {
#ifdef _WIN32
  if (!wsa_inited) {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
      return false;
    wsa_inited = true;
  }
#endif
  return true;
}

void shutdown_network() {
#ifdef _WIN32
  if (wsa_inited) {
    WSACleanup();
    wsa_inited = false;
  }
#endif
}

static int get_fd(const Socket& s) {
#ifdef _WIN32
  return static_cast<int>(s.fd);
#else
  return s.fd;
#endif
}

void close_socket(Socket& s) {
  if (s.fd < 0)
    return;
#ifdef _WIN32
  closesocket(static_cast<SOCKET>(s.fd));
#else
  ::close(s.fd);
#endif
  s.fd = -1;
}

static bool set_nodelay(int fd) {
  int one = 1;
#ifdef _WIN32
  return setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&one),
                    sizeof(one)) == 0;
#else
  return setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one)) == 0;
#endif
}

bool tcp_listen(const std::string& host, uint16_t port, Socket& out) {
  addrinfo hints{};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  hints.ai_flags = AI_PASSIVE;

  std::string port_str = std::to_string(port);
  addrinfo* res = nullptr;
  int gai = getaddrinfo(host.empty() ? nullptr : host.c_str(), port_str.c_str(), &hints, &res);
  if (gai != 0 || !res)
    return false;

  int fd = -1;
  for (addrinfo* p = res; p; p = p->ai_next) {
#ifdef _WIN32
    fd = static_cast<int>(socket(p->ai_family, p->ai_socktype, p->ai_protocol));
    if (fd == static_cast<int>(INVALID_SOCKET))
      continue;
#else
    fd = ::socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (fd < 0)
      continue;
#endif
    int yes = 1;
#ifdef _WIN32
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&yes), sizeof(yes));
#else
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
#endif
    if (bind(fd, p->ai_addr, static_cast<socklen_t>(p->ai_addrlen)) == 0) {
      if (listen(fd, SOMAXCONN) == 0)
        break;
    }
#ifdef _WIN32
    closesocket(fd);
#else
    ::close(fd);
#endif
    fd = -1;
  }
  freeaddrinfo(res);
  if (fd < 0)
    return false;
  set_nodelay(fd);
#ifdef _WIN32
  out.fd = static_cast<int>(fd);
#else
  out.fd = fd;
#endif
  return true;
}

bool tcp_accept(const Socket& listener, Socket& client, std::string& peer_host) {
  sockaddr_storage ss{};
  socklen_t slen = sizeof(ss);
#ifdef _WIN32
  SOCKET c = accept(static_cast<SOCKET>(get_fd(listener)), reinterpret_cast<sockaddr*>(&ss), &slen);
  if (c == INVALID_SOCKET)
    return false;
  client.fd = static_cast<int>(c);
#else
  int c = ::accept(get_fd(listener), reinterpret_cast<sockaddr*>(&ss), &slen);
  if (c < 0)
    return false;
  client.fd = c;
#endif
  char hbuf[NI_MAXHOST]{};
  if (getnameinfo(reinterpret_cast<sockaddr*>(&ss), slen, hbuf, sizeof(hbuf), nullptr, 0,
                  NI_NUMERICHOST) == 0)
    peer_host = hbuf;
  set_nodelay(get_fd(client));
  return true;
}

bool tcp_connect(const std::string& host, uint16_t port, Socket& out) {
  addrinfo hints{};
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;

  std::string port_str = std::to_string(port);
  addrinfo* res = nullptr;
  if (getaddrinfo(host.c_str(), port_str.c_str(), &hints, &res) != 0 || !res)
    return false;

  int fd = -1;
  for (addrinfo* p = res; p; p = p->ai_next) {
#ifdef _WIN32
    fd = static_cast<int>(socket(p->ai_family, p->ai_socktype, p->ai_protocol));
    if (fd == static_cast<int>(INVALID_SOCKET))
      continue;
#else
    fd = ::socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (fd < 0)
      continue;
#endif
    if (connect(fd, p->ai_addr, static_cast<socklen_t>(p->ai_addrlen)) == 0)
      break;
#ifdef _WIN32
    closesocket(fd);
#else
    ::close(fd);
#endif
    fd = -1;
  }
  freeaddrinfo(res);
  if (fd < 0)
    return false;
  set_nodelay(fd);
#ifdef _WIN32
  out.fd = static_cast<int>(fd);
#else
  out.fd = fd;
#endif
  return true;
}

bool send_all(const Socket& s, const void* data, size_t len) {
  const char* p = static_cast<const char*>(data);
  size_t off = 0;
  while (off < len) {
#ifdef _WIN32
    int n = send(static_cast<SOCKET>(get_fd(s)), p + off, static_cast<int>(len - off), 0);
#else
    ssize_t n = ::send(get_fd(s), p + off, len - off, 0);
#endif
    if (n <= 0)
      return false;
    off += static_cast<size_t>(n);
  }
  return true;
}

bool recv_all(const Socket& s, void* data, size_t len) {
  char* p = static_cast<char*>(data);
  size_t off = 0;
  while (off < len) {
#ifdef _WIN32
    int n = recv(static_cast<SOCKET>(get_fd(s)), p + off, static_cast<int>(len - off), 0);
#else
    ssize_t n = ::recv(get_fd(s), p + off, len - off, 0);
#endif
    if (n <= 0)
      return false;
    off += static_cast<size_t>(n);
  }
  return true;
}

} // namespace hcp::net
