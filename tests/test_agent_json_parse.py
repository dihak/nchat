#!/usr/bin/env python3
# test_agent_json_parse.py — protocol shape checks for agent control JSON
#
# Copyright (c) 2026 Kristofer Berggren
# All rights reserved.
#
# nchat is distributed under the MIT license, see LICENSE for details.

"""Lightweight checks mirroring C++ agent request validation expectations."""

from __future__ import annotations

import json
import re
import sys


def looks_like_object(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("{")


def extract_string(obj_src: str, key: str):
    # Same rough approach as the C++ AgentExtractString (not a full JSON parser).
    m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"', obj_src)
    if not m:
        return None
    return json.loads('"' + m.group(1) + '"')


def classify(line: str) -> dict:
    """Return the response shape the C++ side should produce for common cases."""
    id_val = ""
    if not looks_like_object(line):
        return {"id": id_val, "ok": False, "error": "malformed JSON"}
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        # C++ extractor may still pull id/method from broken JSON; treat as malformed.
        return {"id": id_val, "ok": False, "error": "malformed JSON"}
    if not isinstance(data, dict):
        return {"id": id_val, "ok": False, "error": "malformed JSON"}
    id_val = str(data.get("id", ""))
    method = data.get("method")
    if not isinstance(method, str) or not method:
        return {"id": id_val, "ok": False, "error": "malformed JSON: missing method"}
    if method not in ("chats", "history", "send", "send_file"):
        return {"id": id_val, "ok": False, "error": f"unknown method: {method}"}
    if method == "send":
        params = data.get("params") or {}
        if not params.get("text"):
            return {"id": id_val, "ok": False, "error": "empty text"}
    return {"id": id_val, "ok": True, "method": method}


def agent_json_unescape(s: str) -> str:
    """Mirror of C++ AgentJsonUnescape (\\uXXXX -> UTF-8)."""
    out: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            esc = s[i + 1]
            if esc == '"':
                out.append('"')
                i += 2
            elif esc == "\\":
                out.append("\\")
                i += 2
            elif esc == "/":
                out.append("/")
                i += 2
            elif esc == "b":
                out.append("\b")
                i += 2
            elif esc == "f":
                out.append("\f")
                i += 2
            elif esc == "n":
                out.append("\n")
                i += 2
            elif esc == "r":
                out.append("\r")
                i += 2
            elif esc == "t":
                out.append("\t")
                i += 2
            elif esc == "u" and i + 5 < len(s):
                hexpart = s[i + 2 : i + 6]
                try:
                    code = int(hexpart, 16)
                    if 0xD800 <= code <= 0xDFFF:
                        out.append(s[i])
                        i += 1
                    else:
                        out.append(chr(code))
                        i += 6
                except ValueError:
                    out.append(s[i])
                    i += 1
            else:
                out.append(s[i])
                i += 1
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def test_unicode_unescape() -> None:
    assert agent_json_unescape("hello") == "hello"
    assert agent_json_unescape(r"a\nb") == "a\nb"
    assert agent_json_unescape(r"say \"hi\"") == 'say "hi"'
    assert agent_json_unescape(r"\u0041") == "A"
    assert agent_json_unescape(r"\u00e9") == "é"
    assert agent_json_unescape(r"\u4e2d") == "中"
    assert agent_json_unescape(r"x\u0020y") == "x y"


def main() -> int:
    cases = [
        ("not json", False, "malformed"),
        ('{"id":"1"}', False, "missing method"),
        ('{"id":"1","method":"nope","params":{}}', False, "unknown method"),
        ('{"id":"1","method":"chats","params":{}}', True, None),
        ('{"id":"1","method":"send","params":{"chat":"c","text":""}}', False, "empty text"),
        ('{"id":"1","method":"send","params":{"chat":"c","text":"hi"}}', True, None),
        ('{"id":"1","method":"history","params":{"chat":"c","limit":30}}', True, None),
    ]
    failed = 0
    for line, expect_ok, err_sub in cases:
        resp = classify(line)
        if resp["ok"] != expect_ok:
            print(f"FAIL: ok mismatch for {line!r}: {resp}", file=sys.stderr)
            failed += 1
            continue
        if not expect_ok and err_sub and err_sub not in resp.get("error", ""):
            print(f"FAIL: error text for {line!r}: {resp}", file=sys.stderr)
            failed += 1
            continue
        print(f"ok: {line[:40]!r} -> ok={resp['ok']}")
    try:
        test_unicode_unescape()
        print("ok: unicode unescape")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: unicode unescape: {exc}", file=sys.stderr)
        failed += 1
    if failed:
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
