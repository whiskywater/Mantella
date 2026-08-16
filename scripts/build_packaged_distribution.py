#!/usr/bin/env python3
"""Build and gate a complete Mantella onedir distribution."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    source = args.source.resolve()
    dist = args.dist.resolve()
    work = args.work.resolve()

    run([sys.executable, str(source / "scripts" / "validate_packaging_environment.py")], source)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            str(source / "packaging" / "Mantella.spec"),
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
        ],
        source,
    )

    package = dist / "Mantella"
    internal = package / "_internal"
    required = [package / "Mantella.exe", internal / "gradio_client", internal / "gradio" / "blocks_events.py", internal / "gradio_client" / "types.json"]
    missing = [str(path) for path in required if not path.exists()]
    tk_binary = list(internal.glob("_tkinter*.pyd")) + list(internal.glob("**/_tkinter*.pyd"))
    if not tk_binary and not (internal / "tkinter").exists():
        missing.append(f"{internal} (Tk runtime: tkinter package or _tkinter DLL)")
    if missing:
        raise SystemExit("Packaged distribution is incomplete:\n" + "\n".join(missing))

    run(
        [
            sys.executable,
            str(source / "scripts" / "run_packaged_startup_smoke.py"),
            "--exe",
            str(package / "Mantella.exe"),
            "--working-dir",
            str(package),
            "--timeout",
            str(args.timeout),
        ],
        source,
    )
    print(f"PASS complete packaged distribution: {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
