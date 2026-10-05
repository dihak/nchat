// uientryview.cpp
//
// Copyright (c) 2019-2025 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#include "uientryview.h"

#include <algorithm>

#include "strutil.h"
#include "uicolorconfig.h"
#include "uimodel.h"

UiEntryView::UiEntryView(const UiViewParams& p_Params)
  : UiViewBase(p_Params)
{
}

void UiEntryView::Draw()
{
  if (!m_Enabled) return;

  if (!m_Dirty)
  {
    wmove(m_Win, m_CursY, m_CursX);
    wrefresh(m_Win);
    return;
  }

  m_Dirty = false;

  curs_set(0);

  const bool showAsk = (m_H > 1);
  const int messageH = showAsk ? (m_H - 1) : m_H;
  std::wstring input = m_Model->GetEntryStrLocked();
  const int inputPos = m_Model->GetEntryPosLocked();
  const bool askFocus = showAsk && m_Model->GetAskFocusLocked();
  std::wstring line;
  std::vector<std::wstring> lines;
  int cx = 0;
  int cy = 0;
  lines = StrUtil::WordWrap(input, m_W, false, false, false, 2, inputPos, cy, cx);

  static int colorPair = UiColorConfig::GetColorPair("entry_color");
  static int attribute = UiColorConfig::GetAttribute("entry_attr");

  werase(m_Win);
  wbkgd(m_Win, attribute | colorPair | ' ');
  wattron(m_Win, attribute | colorPair);

  int yoffs = (cy < (messageH - 1)) ? 0 : (cy - (messageH - 1));

  for (int i = 0; i < messageH; ++i)
  {
    if ((i + yoffs) < (int)lines.size())
    {
      line = lines.at(i + yoffs).c_str();
      line.erase(std::remove(line.begin(), line.end(), EMOJI_PAD), line.end());
      mvwaddwstr(m_Win, i, 0, line.c_str());
    }
  }

  if (showAsk)
  {
    const std::wstring prefix = L"ai: ";
    std::wstring ask = m_Model->GetAskStrLocked();
    const int askPos = m_Model->GetAskPosLocked();
    const int avail = std::max(1, m_W - (int)prefix.size());
    int offset = 0;
    if (askPos >= avail)
    {
      offset = askPos - avail + 1;
    }
    std::wstring shown = ask.substr(std::min(offset, (int)ask.size()));
    if ((int)shown.size() > avail)
    {
      shown = shown.substr(0, avail);
    }
    mvwaddwstr(m_Win, m_H - 1, 0, (prefix + shown).c_str());
    if (askFocus)
    {
      cx = (int)prefix.size() + askPos - offset;
      cy = m_H - 1;
      yoffs = 0;
    }
  }

  wattroff(m_Win, attribute | colorPair);

  m_CursX = cx;
  m_CursY = askFocus ? cy : (cy - yoffs);

  wmove(m_Win, m_CursY, m_CursX);
  wrefresh(m_Win);
}
