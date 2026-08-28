# -*- mode: python ; coding: utf-8 -*-
"""LocalFlow 单文件发布规格；前端和内置插件示例均嵌入可执行文件。"""
from pathlib import Path

from PyInstaller.building.api import EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
spec_path = Path(SPECPATH).resolve()
repo_root = spec_path if (spec_path / "pyproject.toml").is_file() else spec_path.parent
entry = repo_root / "src" / "localflow" / "__main__.py"
frontend_dist = repo_root / "frontend" / "dist"
starter_scripts = repo_root / "src" / "localflow" / "starter_root" / "scripts"

if not entry.is_file():
    raise SystemExit(f"missing entry point: {entry}")
if not (frontend_dist / "index.html").is_file():
    raise SystemExit("frontend/dist is missing; build the offline frontend first")

datas = collect_data_files("localflow")
datas.append((str(frontend_dist), "frontend/dist"))
datas.append((str(starter_scripts), "localflow/starter_root/scripts"))

a = Analysis(
    [str(entry)], pathex=[str(repo_root / "src")], binaries=[], datas=datas,
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("watchfiles"),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="localflow", debug=False,
    bootloader_ignore_signals=True, strip=False, upx=False, console=True,
    disable_windowed_traceback=False,
)
