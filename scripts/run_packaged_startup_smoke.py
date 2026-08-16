#!/usr/bin/env python3
"""Fail-fast startup smoke test for an onedir Mantella executable.

This intentionally tests the packaged bootstrap, not source imports.  The
working directory must contain the executable's ``_internal`` directory and a
representative config.ini/custom_user_folder.ini.
"""

from __future__ import annotations

import argparse
import shutil
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


FAILURE_MARKERS = (
    "Traceback (most recent call last)",
    "ModuleNotFoundError",
    "ImportError",
    "FileNotFoundError",
    "DLL load failed",
    "Unable to load", 
)


def _ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=1) as response:
            return response.status < 500
    except (OSError, URLError):
        return False


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--working-dir", type=Path)
    parser.add_argument("--config-template", type=Path)
    parser.add_argument("--ready-url", default="http://127.0.0.1:4999/ui")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    exe = args.exe.resolve()
    workdir = (args.working_dir or exe.parent).resolve()
    if not exe.is_file():
        print(f"FAIL packaged startup: executable not found: {exe}", file=sys.stderr)
        return 2
    if not (workdir / "_internal").is_dir():
        print(f"FAIL packaged startup: missing _internal beside {exe}", file=sys.stderr)
        return 2

    config_path = workdir / "config.ini"
    config_backup = workdir / "config.ini.packaged-smoke-backup"
    if args.config_template:
        if not args.config_template.is_file():
            print(f"FAIL packaged startup: config template not found: {args.config_template}", file=sys.stderr)
            return 2
        if config_path.exists():
            shutil.copy2(config_path, config_backup)
        shutil.copy2(args.config_template, config_path)
    elif not config_path.exists():
        print(f"FAIL packaged startup: missing config.ini in {workdir}", file=sys.stderr)
        return 2

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [str(exe)],
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        start_new_session=(os.name != "nt"),
    )
    deadline = time.monotonic() + args.timeout
    success = False
    failure_message = ""
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                output = stdout + "\n" + stderr
                print(output, end="")
                failure_message = f"FAIL packaged startup: exited early with code {process.returncode}"
                break
            if _ready(args.ready_url):
                print(f"PASS packaged startup: ready at {args.ready_url}")
                success = True
                break
            time.sleep(0.2)
        else:
            failure_message = f"FAIL packaged startup: readiness timeout ({args.ready_url})"
    finally:
        if args.config_template:
            if config_backup.exists():
                shutil.move(config_backup, config_path)
            else:
                config_path.unlink(missing_ok=True)
        _terminate(process)
        stdout, stderr = process.communicate(timeout=5)
        output = stdout + "\n" + stderr
        if any(marker in output for marker in FAILURE_MARKERS):
            print(output, end="")
            success = False
            failure_message = "FAIL packaged startup: packaged process reported an unhandled runtime error"
    if not success:
        print(failure_message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
