// uicontroller.cpp
//
// Copyright (c) 2019-2026 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#include "uicontroller.h"

#include <cwchar>

#include <unistd.h>
#include <sys/select.h>

#include "uikeyinput.h"

UiController::UiController()
{
}

UiController::~UiController()
{
}

void UiController::Init()
{
}

void UiController::Cleanup()
{
}

wint_t UiController::GetKey(int p_TimeOutMs, int p_WakeFd, bool* p_Woke)
{
  if (p_Woke != nullptr)
  {
    *p_Woke = false;
  }

  fd_set fds;
  FD_ZERO(&fds);
  FD_SET(STDIN_FILENO, &fds);
  int maxfd = STDIN_FILENO;
  if (p_WakeFd >= 0)
  {
    FD_SET(p_WakeFd, &fds);
    if (p_WakeFd > maxfd) maxfd = p_WakeFd;
  }
  struct timeval tv = { (p_TimeOutMs / 1000), (p_TimeOutMs % 1000) * 1000 };
  wint_t key = 0;
  select(maxfd + 1, &fds, NULL, NULL, &tv); // ignore select() rv to get resize events
  if ((p_WakeFd >= 0) && FD_ISSET(p_WakeFd, &fds) && (p_Woke != nullptr))
  {
    *p_Woke = true;
  }
  if (FD_ISSET(STDIN_FILENO, &fds))
  {
    UiKeyInput::GetWch(&key);
  }

  return key;
}
