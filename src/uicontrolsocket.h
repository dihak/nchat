// uicontrolsocket.h
//
// Copyright (c) 2026 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#pragma once

#include <atomic>
#include <condition_variable>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

class UiModel;

// Unix-domain control socket for agent access while the TUI is running.
// Accept/read runs on a background thread; work is posted to the UI thread via
// a self-pipe and completed under the model mutex (see ProcessOnUiThread).
class UiControlSocket
{
public:
  UiControlSocket();
  ~UiControlSocket();

  // confdir/control.sock; unlinks stale path. No-op on non-Unix.
  bool Start(const std::string& p_ConfDir, std::shared_ptr<UiModel> p_Model);
  void Stop();

  int GetWakeFd() const { return m_WakeRd; }

  // Drain pending requests on the UI thread. Must not be called from the
  // accept thread. Does not call ncurses.
  void ProcessOnUiThread();

private:
  struct Pending
  {
    std::string request;
    std::string response;
    bool done = false;
    std::mutex mutex;
    std::condition_variable cv;
  };

  void AcceptLoop();
  void HandleClient(int p_ClientFd);
  std::string Submit(const std::string& p_RequestLine);
  void WakeUi();
  void DrainWake();

  std::shared_ptr<UiModel> m_Model;
  std::string m_SockPath;
  int m_ListenFd = -1;
  int m_WakeRd = -1;
  int m_WakeWr = -1;
  std::atomic<bool> m_Running{ false };
  std::thread m_Thread;

  std::mutex m_QueueMutex;
  std::deque<std::shared_ptr<Pending>> m_Queue;

  static const int s_TimeoutSec = 30;
};
