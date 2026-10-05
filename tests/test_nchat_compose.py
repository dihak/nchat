#!/usr/bin/env python3
# test_nchat_compose.py — config parsing tests for nchat-compose (no network)
#
# Copyright (c) 2026 Kristofer Berggren
# All rights reserved.
#
# nchat is distributed under the MIT license, see LICENSE for details.

"""Unit tests for nchat-compose config loading and failure modes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "utils" / "nchat-compose"
HISTORY = ROOT / "doc" / "example-history.txt"


def run_compose(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env is not None:
        full_env.update(env)
        # Drop key env vars unless provided so missing-key tests are stable.
        for k in list(full_env):
            if k.endswith("_API_KEY") and k not in env:
                full_env.pop(k, None)
    return subprocess.run(
        [sys.executable, str(COMPOSE), *args],
        capture_output=True,
        text=True,
        timeout=10,
        env=full_env,
    )


def write_conf(td: Path, text: str) -> Path:
    p = td / "compose.conf"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_config():
    r = run_compose(["-c", str(HISTORY)], env={})
    assert r.returncode != 0
    assert r.stdout == ""
    assert "NCHAT_COMPOSE_CONFIG" in r.stderr or "-f" in r.stderr


def test_missing_required_keys():
    with tempfile.TemporaryDirectory() as td:
        conf = write_conf(Path(td), "model=demo-model\n")
        r = run_compose(["-f", str(conf), "-c", str(HISTORY)], env={})
        assert r.returncode != 0
        assert r.stdout == ""
        assert "missing required key" in r.stderr


def test_missing_api_key():
    with tempfile.TemporaryDirectory() as td:
        conf = write_conf(
            Path(td),
            "\n".join(
                [
                    "base_url=https://api.example.com/v1",
                    "api_backend=responses",
                    "model=demo-model",
                    "api_key_env=NCHAT_COMPOSE_TEST_KEY_A,NCHAT_COMPOSE_TEST_KEY_B",
                    "timeout=5",
                    "",
                ]
            ),
        )
        env = {
            "NCHAT_COMPOSE_TEST_KEY_A": "",
            "NCHAT_COMPOSE_TEST_KEY_B": "",
        }
        r = run_compose(["-f", str(conf), "-c", str(HISTORY)], env=env)
        assert r.returncode != 0
        assert r.stdout == ""
        assert "api_key_env" in r.stderr or "not set" in r.stderr.lower()


def test_unknown_backend():
    with tempfile.TemporaryDirectory() as td:
        conf = write_conf(
            Path(td),
            "\n".join(
                [
                    "base_url=https://api.example.com/v1",
                    "api_backend=not_a_backend",
                    "model=demo-model",
                    "api_key_env=NCHAT_COMPOSE_TEST_KEY",
                    "",
                ]
            ),
        )
        r = run_compose(
            ["-f", str(conf), "-c", str(HISTORY)],
            env={"NCHAT_COMPOSE_TEST_KEY": "secret-for-test-only"},
        )
        assert r.returncode != 0
        assert r.stdout == ""
        assert "unknown api_backend" in r.stderr


def test_env_config_path():
    with tempfile.TemporaryDirectory() as td:
        conf = write_conf(
            Path(td),
            "\n".join(
                [
                    "base_url=https://api.example.com/v1",
                    "api_backend=not_a_backend",
                    "model=demo-model",
                    "api_key_env=NCHAT_COMPOSE_TEST_KEY",
                    "",
                ]
            ),
        )
        r = run_compose(
            ["-c", str(HISTORY)],
            env={
                "NCHAT_COMPOSE_CONFIG": str(conf),
                "NCHAT_COMPOSE_TEST_KEY": "secret-for-test-only",
            },
        )
        assert r.returncode != 0
        assert "unknown api_backend" in r.stderr


def main() -> int:
    if not COMPOSE.is_file():
        print(f"FAIL: missing {COMPOSE}", file=sys.stderr)
        return 1
    tests = [
        test_missing_config,
        test_missing_required_keys,
        test_missing_api_key,
        test_unknown_backend,
        test_env_config_path,
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
