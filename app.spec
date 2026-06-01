# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格：app 单文件可执行程序。

构建：仓库根执行 ./tools/pack.sh（会先构建 frontend/dist，再 PyInstaller，Linux 上 staticx）。
"""
from __future__ import annotations

from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis

block_cipher = None


def _repo_root_from_spec() -> Path:
    spec = Path(SPECPATH).resolve()
    seeds = [spec.parent]
    try:
        seeds.append(Path.cwd().resolve())
    except OSError:
        pass
    for seed in seeds:
        for base in [seed, *seed.parents]:
            if (base / "pyproject.toml").is_file() and (
                base / "src" / "app_main" / "__main__.py"
            ).is_file():
                return base
    return spec.parent


repo_root = _repo_root_from_spec()
entry = repo_root / "src" / "app_main" / "__main__.py"
frontend_dist = repo_root / "frontend" / "dist"

datas = []
if frontend_dist.is_dir():
    datas.append((str(frontend_dist), "frontend/dist"))

a = Analysis(
    [str(entry)],
    pathex=[str(repo_root / "src" / "app_main")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
