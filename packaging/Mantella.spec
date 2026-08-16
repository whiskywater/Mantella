# -*- mode: python ; coding: utf-8 -*-
"""Reproducible onedir build for Mantella.

The build preflight requires a Python installation with Tk support.  Gradio
and gradio_client are collected as complete packages because both load Python
modules and JSON metadata dynamically during UI startup.
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules


source_root = os.path.abspath(os.path.join(SPECPATH, os.pardir))
gradio_datas, gradio_bins, gradio_hidden = collect_all("gradio")
client_datas, client_bins, client_hidden = collect_all("gradio_client")
tk_hidden = collect_submodules("tkinter")

a = Analysis(
    [os.path.join(source_root, "main.py")],
    pathex=[source_root],
    binaries=gradio_bins + client_bins,
    datas=gradio_datas + client_datas + [
        (os.path.join(source_root, "data"), "data"),
        (os.path.join(source_root, "custom_user_folder.ini"), "."),
    ],
    hiddenimports=gradio_hidden + client_hidden + tk_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mantella",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
)
COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Mantella",
)
