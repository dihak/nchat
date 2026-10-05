// uicontroller.h
//
// Copyright (c) 2019-2026 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#pragma once

#include <ncurses.h>

class UiController
{
public:
  UiController();
  virtual ~UiController();

  void Init();
  void Cleanup();

  // p_WakeFd: optional self-pipe read end used by the agent control socket.
  // When readable, *p_Woke is set true so the UI loop can drain control work
  // without calling ncurses from the accept thread.
  static wint_t GetKey(int p_TimeOutMs, int p_WakeFd = -1, bool* p_Woke = nullptr);

private:
};
