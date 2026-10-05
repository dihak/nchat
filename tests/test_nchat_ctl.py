#!/usr/bin/env python3
# test_nchat_ctl.py — fake control.sock server tests for nchat-ctl
#
# Copyright (c) 2026 Kristofer Berggren
# All rights reserved.
#
# nchat is distributed under the MIT license, see LICENSE for details.

"""Unit tests for nchat-ctl against a fake Unix socket (no live nchat)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CTL = ROOT / "utils" / "nchat-ctl"


class FakeServer:
    def __init__(self, sock_path: Path, handler):
        self.sock_path = sock_path
        self.handler = handler
        self._stop = threading.Event()
        self._thread = None
        self.errors = []

    def start(self):
        if self.sock_path.exists():
            self.sock_path.unlink()
        self._serv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._serv.bind(str(self.sock_path))
        self._serv.listen(4)
        self._serv.settimeout(0.2)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._serv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if not buf:
                    continue
                line = buf.splitlines()[0].decode("utf-8", errors="replace")
                try:
                    req = json.loads(line)
                    resp = self.handler(req)
                except Exception as exc:  # noqa: BLE001
                    self.errors.append(exc)
                    resp = {"id": "", "ok": False, "error": f"handler: {exc}"}
                out = (json.dumps(resp) + "\n").encode("utf-8")
                conn.sendall(out)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        try:
            self._serv.close()
        except OSError:
            pass
        if self.sock_path.exists():
            self.sock_path.unlink()


def run_ctl(confdir: Path, args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(CTL), "--confdir", str(confdir), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


def test_missing_socket_exit_2():
    with tempfile.TemporaryDirectory() as td:
        conf = Path(td)
        r = run_ctl(conf, ["chats"])
        assert r.returncode == 2, r.stderr
        assert "TUI is not running" in r.stderr or "control socket missing" in r.stderr


def test_chats_ok():
    with tempfile.TemporaryDirectory() as td:
        conf = Path(td)
        sock = conf / "control.sock"

        def handler(req):
            assert req["method"] == "chats"
            return {
                "id": req["id"],
                "ok": True,
                "result": {
                    "chats": [
                        {
                            "id": "c1",
                            "title": "Alice",
                            "unread": False,
                            "muted": False,
                            "pinned": True,
                            "lastMessageTime": 1,
                        }
                    ]
                },
            }

        srv = FakeServer(sock, handler)
        srv.start()
        try:
            time.sleep(0.05)
            r = run_ctl(conf, ["chats"])
            assert r.returncode == 0, r.stderr
            data = json.loads(r.stdout)
            assert data["chats"][0]["id"] == "c1"
            assert data["chats"][0]["title"] == "Alice"
        finally:
            srv.stop()
        assert not srv.errors


def test_api_error_exit_1():
    with tempfile.TemporaryDirectory() as td:
        conf = Path(td)
        sock = conf / "control.sock"

        def handler(req):
            return {"id": req.get("id", ""), "ok": False, "error": "chat not found"}

        srv = FakeServer(sock, handler)
        srv.start()
        try:
            time.sleep(0.05)
            r = run_ctl(conf, ["history", "--chat", "nope"])
            assert r.returncode == 1
            assert "chat not found" in r.stderr
        finally:
            srv.stop()


def test_malformed_and_unknown_method_protocol():
    """Simulate server responses for malformed / unknown (as the C++ side would)."""
    with tempfile.TemporaryDirectory() as td:
        conf = Path(td)
        sock = conf / "control.sock"
        seen = []

        def handler(req):
            seen.append(req)
            method = req.get("method")
            if method == "nope":
                return {"id": req.get("id", ""), "ok": False, "error": "unknown method: nope"}
            if method == "chats":
                return {"id": req.get("id", ""), "ok": True, "result": {"chats": []}}
            return {"id": req.get("id", ""), "ok": False, "error": "malformed JSON"}

        srv = FakeServer(sock, handler)
        srv.start()
        try:
            time.sleep(0.05)
            r = run_ctl(conf, ["chats"])
            assert r.returncode == 0

            # Direct socket: unknown method
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(sock))
                s.sendall(b'{"id":"x","method":"nope","params":{}}\n')
                buf = b""
                while b"\n" not in buf:
                    buf += s.recv(4096)
                resp = json.loads(buf.splitlines()[0])
                assert resp["ok"] is False
                assert "unknown method" in resp["error"]

            # Direct socket: malformed
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(sock))
                s.sendall(b"not-json\n")
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                # Fake handler gets JSON parse error → ok false
                if buf:
                    resp = json.loads(buf.splitlines()[0])
                    assert resp["ok"] is False
        finally:
            srv.stop()


def test_send_and_history_args():
    with tempfile.TemporaryDirectory() as td:
        conf = Path(td)
        sock = conf / "control.sock"
        seen = []

        def handler(req):
            seen.append(req)
            return {"id": req["id"], "ok": True, "result": {"sent": True, "echo": req}}

        srv = FakeServer(sock, handler)
        srv.start()
        try:
            time.sleep(0.05)
            r = run_ctl(
                conf,
                ["send", "--chat", "c1", "--text", "hi", "--reply-to", "m9"],
            )
            assert r.returncode == 0, r.stderr
            assert seen[-1]["method"] == "send"
            assert seen[-1]["params"]["text"] == "hi"
            assert seen[-1]["params"]["replyTo"] == "m9"

            r = run_ctl(conf, ["history", "--chat", "c1", "--limit", "5"])
            assert r.returncode == 0, r.stderr
            assert seen[-1]["method"] == "history"
            assert seen[-1]["params"]["limit"] == 5
        finally:
            srv.stop()


def main() -> int:
    if not CTL.is_file():
        print(f"FAIL: missing {CTL}", file=sys.stderr)
        return 1
    tests = [
        test_missing_socket_exit_2,
        test_chats_ok,
        test_api_error_exit_1,
        test_malformed_and_unknown_method_protocol,
        test_send_and_history_args,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok: {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL: {fn.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed} failed", file=sys.stderr)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
