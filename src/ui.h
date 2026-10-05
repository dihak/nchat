// ui.h
//
// Copyright (c) 2019-2026 Kristofer Berggren
// All rights reserved.
//
// nchat is distributed under the MIT license, see LICENSE for details.

#pragma once

#include <memory>
#include <string>
#include <unordered_map>

class Protocol;
class ServiceMessage;
class UiController;
class UiControlSocket;
class UiModel;

class Ui
{
public:
  Ui();
  virtual ~Ui();

  void Init();
  void Cleanup();

  void Run();
  void AddProtocol(std::shared_ptr<Protocol> p_Protocol);
  std::unordered_map<std::string, std::shared_ptr<Protocol>> GetProtocols();
  void MessageHandler(std::shared_ptr<ServiceMessage> p_ServiceMessage);

  static void RunKeyDump();

private:
  std::shared_ptr<UiModel> m_Model;
  std::shared_ptr<UiController> m_Controller;
  std::shared_ptr<UiControlSocket> m_ControlSocket;
  std::string m_TerminalTitle;
};
