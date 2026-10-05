#!/usr/bin/env python3
# nchat_mcp.py — MCP stdio server wrapping nchat-ctl
#
# Copyright (c) 2026 Kristofer Berggren
# All rights reserved.
#
# nchat is distributed under the MIT license, see LICENSE for details.

"""Minimal MCP server (stdio JSON-RPC) for nchat agent control."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SERVER_NAME = "nchat"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


def nchat_ctl_path() -> str:
    env = os.environ.get("NCHAT_CTL")
    if env:
        return env
    here = Path(__file__).resolve().parent
    candidate = here / "nchat-ctl"
    if candidate.is_file():
        return str(candidate)
    return "nchat-ctl"


def confdir_for(protocol: str) -> str:
    p = (protocol or "").strip().lower()
    home = Path.home()
    if p == "telegram":
        return os.environ.get("NCHAT_TELEGRAM_DIR") or str(home / ".config" / "nchat-telegram")
    if p == "whatsapp":
        return os.environ.get("NCHAT_WHATSAPP_DIR") or str(home / ".config" / "nchat-whatsapp")
    raise ValueError("protocol must be 'telegram' or 'whatsapp'")


def run_ctl(args: list[str]) -> dict[str, Any]:
    cmd = [nchat_ctl_path(), *args]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {"ok": False, "error": f"nchat-ctl not found ({cmd[0]})"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "nchat-ctl timed out"}

    if proc.returncode == 2:
        return {
            "ok": False,
            "error": (proc.stderr or "").strip()
            or "TUI is not running for that confdir",
        }
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout or "nchat-ctl failed").strip()}
    try:
        return {"ok": True, "result": json.loads(proc.stdout)}
    except json.JSONDecodeError:
        return {"ok": True, "result": proc.stdout}


TOOLS = [
    {
        "name": "nchat_chats",
        "description": "List chats from a running nchat TUI (telegram or whatsapp confdir).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol": {
                    "type": "string",
                    "enum": ["telegram", "whatsapp"],
                    "description": "Which nchat confdir/TUI to query",
                }
            },
            "required": ["protocol"],
        },
    },
    {
        "name": "nchat_history",
        "description": "Fetch recent message history for a chat from the running TUI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "enum": ["telegram", "whatsapp"]},
                "chat_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["protocol", "chat_id"],
        },
    },
    {
        "name": "nchat_send",
        "description": "Send a text message via the running nchat TUI (user's linked device).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "enum": ["telegram", "whatsapp"]},
                "chat_id": {"type": "string"},
                "text": {"type": "string"},
                "reply_to": {"type": "string"},
            },
            "required": ["protocol", "chat_id", "text"],
        },
    },
    {
        "name": "nchat_send_file",
        "description": "Send a regular file via the running nchat TUI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocol": {"type": "string", "enum": ["telegram", "whatsapp"]},
                "chat_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["protocol", "chat_id", "path"],
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        confdir = confdir_for(str(arguments.get("protocol", "")))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if name == "nchat_chats":
        return run_ctl(["--confdir", confdir, "chats"])
    if name == "nchat_history":
        args = ["--confdir", confdir, "history", "--chat", str(arguments["chat_id"])]
        if "limit" in arguments and arguments["limit"] is not None:
            args += ["--limit", str(int(arguments["limit"]))]
        return run_ctl(args)
    if name == "nchat_send":
        args = [
            "--confdir",
            confdir,
            "send",
            "--chat",
            str(arguments["chat_id"]),
            "--text",
            str(arguments["text"]),
        ]
        if arguments.get("reply_to"):
            args += ["--reply-to", str(arguments["reply_to"])]
        return run_ctl(args)
    if name == "nchat_send_file":
        return run_ctl(
            [
                "--confdir",
                confdir,
                "send-file",
                "--chat",
                str(arguments["chat_id"]),
                "--path",
                str(arguments["path"]),
            ]
        )
    return {"ok": False, "error": f"unknown tool: {name}"}


def send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg: dict[str, Any]) -> None:
    mid = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
        )
        return

    if method == "notifications/initialized" or method == "initialized":
        return

    if method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        return

    if method == "tools/call":
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        outcome = call_tool(name, arguments)
        if outcome.get("ok"):
            payload = outcome.get("result")
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            send(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": False,
                    },
                }
            )
        else:
            err = outcome.get("error") or "error"
            send(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "content": [{"type": "text", "text": err}],
                        "isError": True,
                    },
                }
            )
        return

    if method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
        return

    if mid is not None:
        send(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        )


def main() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        handle(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
