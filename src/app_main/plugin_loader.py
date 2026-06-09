from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from automation import all_instances

import plugin_api
from automation.script.registry import all_scripts

_APP_MAIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_MAIN_DIR.parents[1]

LoadKind = Literal["package", "module"]


@dataclass(frozen=True)
class LoadItem:
    kind: LoadKind
    path: Path


def repo_root() -> Path:
    return _REPO_ROOT


def default_plugin_paths() -> list[Path]:
    plugins_dir = _REPO_ROOT / "plugins"
    if plugins_dir.is_dir():
        return [plugins_dir]
    return []


def _skip_dir_name(name: str) -> bool:
    return name.startswith(".") or name == "__pycache__"


def _expand_source_path(path: Path) -> list[LoadItem]:
    """把 source 目录或文件展开为待加载项。"""
    if not path.is_dir():
        if path.suffix != ".py":
            raise ValueError(f"source 须为目录或 .py 文件: {path}")
        return [LoadItem("module", path.resolve())]

    path = path.resolve()
    if (path / "__init__.py").is_file():
        return [LoadItem("package", path)]

    items: list[LoadItem] = []
    for child in sorted(path.iterdir()):
        if _skip_dir_name(child.name):
            continue
        if child.is_dir():
            if (child / "__init__.py").is_file():
                items.append(LoadItem("package", child.resolve()))
        elif child.suffix == ".py" and child.name != "__init__.py":
            items.append(LoadItem("module", child.resolve()))

    if not items:
        raise ValueError(f"目录下未找到插件子目录或示例 .py 文件: {path}")
    return items


def collect_plugin_dirs(paths: list[Path]) -> list[Path]:
    """展开 source 路径，仅返回插件包目录（兼容旧调用）。"""
    dirs: list[Path] = []
    seen: set[Path] = set()
    for item in collect_load_items(paths):
        if item.kind == "package" and item.path not in seen:
            seen.add(item.path)
            dirs.append(item.path)
    return dirs


def collect_load_items(paths: list[Path]) -> list[LoadItem]:
    """把配置中的 sources 展开为待加载项。"""
    items: list[LoadItem] = []
    seen: set[tuple[LoadKind, Path]] = set()

    for raw in paths:
        path = raw.expanduser().resolve()
        for item in _expand_source_path(path):
            key = (item.kind, item.path)
            if key not in seen:
                seen.add(key)
                items.append(item)
    return items


def _sanitize_part(part: str, index: int) -> str:
    stem = re.sub(r"[^0-9a-zA-Z_]", "_", part)
    if not stem or stem[0].isdigit():
        return f"p_{index}"
    return stem


def _qualified_name(path: Path, index: int, used: set[str]) -> str:
    try:
        rel = path.relative_to(_REPO_ROOT)
    except ValueError:
        parent = _sanitize_part(path.parent.name, index)
        stem = _sanitize_part(path.stem if path.is_file() else path.name, index)
        rel = Path(parent) / stem

    if path.is_file():
        parts = [_sanitize_part(part, index) for part in rel.parent.parts]
        parts.append(_sanitize_part(rel.stem, index))
    else:
        parts = [_sanitize_part(part, index) for part in rel.parts]

    name = ".".join(parts)
    if name in used:
        name = f"{name}_{index}"
    used.add(name)
    return name


def _ensure_repo_path() -> None:
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _ensure_app_main_path() -> None:
    app_main = str(_APP_MAIN_DIR)
    if app_main not in sys.path:
        sys.path.insert(0, app_main)


def _ensure_parent_packages(qualified_name: str) -> None:
    parts = qualified_name.split(".")
    for i in range(1, len(parts)):
        parent_name = ".".join(parts[:i])
        if parent_name in sys.modules:
            continue
        parent_dir = _REPO_ROOT.joinpath(*parts[:i])
        init_file = parent_dir / "__init__.py"
        if init_file.is_file():
            _load_package(parent_dir, parent_name)
        else:
            _register_namespace_package(parent_name, parent_dir)


def _register_namespace_package(package_name: str, package_dir: Path) -> None:
    import types

    module = types.ModuleType(package_name)
    module.__path__ = [str(package_dir)]  # type: ignore[attr-defined]
    sys.modules[package_name] = module


def _load_package(package_dir: Path, package_name: str) -> str:
    package_dir = package_dir.resolve()
    init_file = package_dir / "__init__.py"
    if not init_file.is_file():
        raise ImportError(f"插件包缺少 __init__.py: {package_dir}")
    _ensure_repo_path()
    _ensure_app_main_path()
    _ensure_parent_packages(package_name)

    spec = importlib.util.spec_from_file_location(
        package_name,
        init_file,
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载插件包: {package_dir}")

    module = importlib.util.module_from_spec(spec)
    module.__package__ = package_name
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return package_name


def _load_module(py_file: Path, module_name: str) -> str:
    py_file = py_file.resolve()
    _ensure_repo_path()
    _ensure_app_main_path()
    _ensure_parent_packages(module_name)

    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {py_file}")

    module = importlib.util.module_from_spec(spec)
    parent = module_name.rpartition(".")[0]
    module.__package__ = parent or None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module_name


def load_plugin_package(plugin_dir: Path, package_name: str) -> str:
    """导入插件包；包内子模块可用相对导入。"""
    return _load_package(plugin_dir, package_name)


def load_plugins(paths: list[Path]) -> list[Path]:
    """按 sources 加载插件与示例；返回已加载的插件包目录。"""
    load_items = collect_load_items(paths)
    loaded_packages: list[Path] = []
    loaded_names: list[str] = []
    before = len(all_instances())
    used_names: set[str] = set()

    for index, item in enumerate(load_items):
        qualified = _qualified_name(item.path, index, used_names)
        if item.kind == "package":
            _load_package(item.path, qualified)
            loaded_packages.append(item.path)
        else:
            _load_module(item.path, qualified)
        loaded_names.append(qualified)

    automations = all_instances()[before:]
    action_names = sorted(plugin_api.all_actions())
    scripts = all_scripts()

    if load_items:
        print(f"已加载 {len(load_items)} 个 source 项")
        for item, name in zip(load_items, loaded_names, strict=True):
            label = "包" if item.kind == "package" else "模块"
            print(f"  - {name} ({label}, {item.path})")
    if automations:
        print(f"已注册 {len(automations)} 个 Automation: {[a.name for a in automations]}")
    if action_names:
        print(f"已注册动作: {', '.join(action_names)}")
    if scripts:
        labels = [f"{s.name}({s.instance_id[:8]})" for s in scripts]
        print(f"已注册 Script: {', '.join(labels)}")

    return loaded_packages
