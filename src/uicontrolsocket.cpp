// uicontrolsocket.cpp
//
// Copyright (c) 2026 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#include "uicontrolsocket.h"

#include "log.h"
#include "uimodel.h"

#if defined(__unix__) || defined(__APPLE__)

#include <cerrno>
#include <cstring>
#include <chrono>

#include <fcntl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace
{
  void SetCloexec(int p_Fd)
  {
    if (p_Fd < 0) return;
    int flags = fcntl(p_Fd, F_GETFD);
    if (flags >= 0)
    {
      fcntl(p_Fd, F_SETFD, flags | FD_CLOEXEC);
    }
  }

  void SetNonblock(int p_Fd)
  {
    if (p_Fd < 0) return;
    int flags = fcntl(p_Fd, F_GETFL);
    if (flags >= 0)
    {
      fcntl(p_Fd, F_SETFL, flags | O_NONBLOCK);
    }
  }
}

UiControlSocket::UiControlSocket()
{
}

UiControlSocket::~UiControlSocket()
{
  Stop();
}

bool UiControlSocket::Start(const std::string& p_ConfDir, std::shared_ptr<UiModel> p_Model)
{
  if (m_Running.load()) return true;
  if (!p_Model || p_ConfDir.empty()) return false;

  m_Model = p_Model;
  m_SockPath = p_ConfDir + "/control.sock";

  int wake[2] = { -1, -1 };
  if (pipe(wake) != 0)
  {
    LOG_WARNING("control socket: pipe failed: %s", strerror(errno));
    return false;
  }
  m_WakeRd = wake[0];
  m_WakeWr = wake[1];
  SetCloexec(m_WakeRd);
  SetCloexec(m_WakeWr);
  SetNonblock(m_WakeRd);
  SetNonblock(m_WakeWr);

  unlink(m_SockPath.c_str());

  m_ListenFd = socket(AF_UNIX, SOCK_STREAM, 0);
  if (m_ListenFd < 0)
  {
    LOG_WARNING("control socket: socket failed: %s", strerror(errno));
    Stop();
    return false;
  }
  SetCloexec(m_ListenFd);

  sockaddr_un addr;
  memset(&addr, 0, sizeof(addr));
  addr.sun_family = AF_UNIX;
  if (m_SockPath.size() >= sizeof(addr.sun_path))
  {
    LOG_WARNING("control socket: path too long");
    Stop();
    return false;
  }
  strncpy(addr.sun_path, m_SockPath.c_str(), sizeof(addr.sun_path) - 1);

  if (bind(m_ListenFd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0)
  {
    LOG_WARNING("control socket: bind failed: %s", strerror(errno));
    Stop();
    return false;
  }

  if (chmod(m_SockPath.c_str(), S_IRUSR | S_IWUSR) != 0)
  {
    LOG_WARNING("control socket: chmod failed: %s", strerror(errno));
  }

  if (listen(m_ListenFd, 8) != 0)
  {
    LOG_WARNING("control socket: listen failed: %s", strerror(errno));
    Stop();
    return false;
  }

  m_Running.store(true);
  m_Thread = std::thread(&UiControlSocket::AcceptLoop, this);
  LOG_INFO("control socket listening on %s", m_SockPath.c_str());
  return true;
}

void UiControlSocket::Stop()
{
  const bool wasRunning = m_Running.exchange(false);
  if (m_ListenFd >= 0)
  {
    shutdown(m_ListenFd, SHUT_RDWR);
    close(m_ListenFd);
    m_ListenFd = -1;
  }
  if (m_WakeWr >= 0)
  {
    // Unblock accept thread select if needed; WakeUi is enough for queue.
    const char b = 0;
    ssize_t ignored = write(m_WakeWr, &b, 1);
    (void)ignored;
  }
  if (wasRunning && m_Thread.joinable())
  {
    m_Thread.join();
  }
  if (m_WakeRd >= 0)
  {
    close(m_WakeRd);
    m_WakeRd = -1;
  }
  if (m_WakeWr >= 0)
  {
    close(m_WakeWr);
    m_WakeWr = -1;
  }
  if (!m_SockPath.empty())
  {
    unlink(m_SockPath.c_str());
    m_SockPath.clear();
  }
  {
    std::lock_guard<std::mutex> lock(m_QueueMutex);
    for (auto& pending : m_Queue)
    {
      std::lock_guard<std::mutex> plock(pending->mutex);
      if (!pending->done)
      {
        pending->response = "{\"id\":\"\",\"ok\":false,\"error\":\"control socket stopped\"}";
        pending->done = true;
        pending->cv.notify_all();
      }
    }
    m_Queue.clear();
  }
  m_Model.reset();
}

void UiControlSocket::WakeUi()
{
  if (m_WakeWr < 0) return;
  const char b = 1;
  ssize_t ignored = write(m_WakeWr, &b, 1);
  (void)ignored;
}

void UiControlSocket::DrainWake()
{
  if (m_WakeRd < 0) return;
  char buf[64];
  while (read(m_WakeRd, buf, sizeof(buf)) > 0)
  {
  }
}

void UiControlSocket::AcceptLoop()
{
  while (m_Running.load())
  {
    fd_set fds;
    FD_ZERO(&fds);
    if (m_ListenFd < 0) break;
    FD_SET(m_ListenFd, &fds);
    struct timeval tv = { 1, 0 };
    const int rv = select(m_ListenFd + 1, &fds, nullptr, nullptr, &tv);
    if (!m_Running.load()) break;
    if (rv < 0)
    {
      if (errno == EINTR) continue;
      LOG_WARNING("control socket: select failed: %s", strerror(errno));
      break;
    }
    if (rv == 0) continue;
    if (!FD_ISSET(m_ListenFd, &fds)) continue;

    const int client = accept(m_ListenFd, nullptr, nullptr);
    if (client < 0)
    {
      if (errno == EINTR || errno == EAGAIN) continue;
      if (!m_Running.load()) break;
      LOG_WARNING("control socket: accept failed: %s", strerror(errno));
      continue;
    }
    SetCloexec(client);
    HandleClient(client);
    close(client);
  }
}

void UiControlSocket::HandleClient(int p_ClientFd)
{
  std::string buffer;
  char chunk[1024];
  while (m_Running.load())
  {
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(p_ClientFd, &fds);
    struct timeval tv = { 1, 0 };
    const int rv = select(p_ClientFd + 1, &fds, nullptr, nullptr, &tv);
    if (!m_Running.load()) break;
    if (rv < 0)
    {
      if (errno == EINTR) continue;
      break;
    }
    if (rv == 0) continue;
    const ssize_t n = read(p_ClientFd, chunk, sizeof(chunk));
    if (n == 0) break;
    if (n < 0)
    {
      if (errno == EINTR) continue;
      break;
    }
    buffer.append(chunk, static_cast<size_t>(n));
    size_t pos = 0;
    while (true)
    {
      const size_t nl = buffer.find('\n', pos);
      if (nl == std::string::npos)
      {
        buffer.erase(0, pos);
        break;
      }
      std::string line = buffer.substr(pos, nl - pos);
      pos = nl + 1;
      if (!line.empty() && line.back() == '\r') line.pop_back();
      if (line.empty()) continue;

      const std::string response = Submit(line);
      std::string out = response;
      if (out.empty() || out.back() != '\n') out.push_back('\n');
      const char* data = out.data();
      size_t left = out.size();
      while (left > 0)
      {
        const ssize_t w = write(p_ClientFd, data, left);
        if (w < 0)
        {
          if (errno == EINTR) continue;
          return;
        }
        data += w;
        left -= static_cast<size_t>(w);
      }
    }
  }
}

std::string UiControlSocket::Submit(const std::string& p_RequestLine)
{
  auto pending = std::make_shared<Pending>();
  pending->request = p_RequestLine;
  {
    std::lock_guard<std::mutex> lock(m_QueueMutex);
    m_Queue.push_back(pending);
  }
  WakeUi();

  std::unique_lock<std::mutex> lock(pending->mutex);
  const bool ok = pending->cv.wait_for(lock, std::chrono::seconds(s_TimeoutSec),
                                       [&]() { return pending->done || !m_Running.load(); });
  if (!ok || !pending->done)
  {
    return "{\"id\":\"\",\"ok\":false,\"error\":\"timeout waiting for UI thread\"}";
  }
  return pending->response;
}

void UiControlSocket::ProcessOnUiThread()
{
  DrainWake();
  while (true)
  {
    std::shared_ptr<Pending> pending;
    {
      std::lock_guard<std::mutex> lock(m_QueueMutex);
      if (m_Queue.empty()) break;
      pending = m_Queue.front();
      m_Queue.pop_front();
    }
    if (!pending) continue;

    std::string response;
    if (m_Model)
    {
      response = m_Model->AgentControl(pending->request);
    }
    else
    {
      response = "{\"id\":\"\",\"ok\":false,\"error\":\"model not available\"}";
    }

    {
      std::lock_guard<std::mutex> lock(pending->mutex);
      pending->response = response;
      pending->done = true;
    }
    pending->cv.notify_all();
  }
}

#else // !unix

UiControlSocket::UiControlSocket()
{
}

UiControlSocket::~UiControlSocket()
{
}

bool UiControlSocket::Start(const std::string&, std::shared_ptr<UiModel>)
{
  return false;
}

void UiControlSocket::Stop()
{
}

void UiControlSocket::ProcessOnUiThread()
{
}

void UiControlSocket::AcceptLoop()
{
}

void UiControlSocket::HandleClient(int)
{
}

std::string UiControlSocket::Submit(const std::string&)
{
  return std::string();
}

void UiControlSocket::WakeUi()
{
}

void UiControlSocket::DrainWake()
{
}

#endif
