#!/usr/bin/env bash
# 构建新前端和 PyInstaller onefile；默认继续完成 staticx 发布资产。
# PACK_SKIP_FRONTEND_BUILD=1 仅供 CI 在宿主机已完成 npm ci/build 后使用。
# PACK_STATICX_SOURCE_BUILD=1 在兼容基线内从源码构建 StaticX，避免下游宿主替换加载器。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BOOTSTRAP="${PACK_PYTHON:-python3}"
if [[ ! -x "$ROOT/.venv-release/bin/python" ]]; then
  rm -rf "$ROOT/.venv-release"
  "$PYTHON_BOOTSTRAP" -m venv "$ROOT/.venv-release"
fi
PYTHON="$ROOT/.venv-release/bin/python"
export PATH="$(dirname "$PYTHON"):$PATH"

if [[ "${PACK_SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
  npm --prefix frontend ci
  npm --prefix frontend run build
fi
test -f frontend/dist/index.html || { echo "frontend/dist/index.html is missing" >&2; exit 1; }

if [[ "${PACK_SKIP_PYTHON_INSTALL:-0}" != "1" ]]; then
  "$PYTHON" -m pip install --upgrade pip setuptools wheel
  "$PYTHON" -m pip install --upgrade --force-reinstall . "pyinstaller>=6,<7"
fi

rm -rf build dist
"$PYTHON" -m PyInstaller --clean --noconfirm app.spec
test -x dist/localflow || { echo "PyInstaller did not produce dist/localflow" >&2; exit 1; }
mv dist/localflow dist/localflow.pyinstaller

if [[ "${PACK_STATICX_SOURCE_BUILD:-0}" == "1" ]]; then
  "$PYTHON" -m pip install --upgrade --force-reinstall scons
  "$PYTHON" -m pip install --upgrade --force-reinstall --no-cache-dir --no-build-isolation --no-binary=staticx "staticx>=0.14,<1"
elif [[ ! -x "$ROOT/.venv-release/bin/staticx" ]]; then
  "$PYTHON" -m pip install "staticx>=0.14,<1"
fi
PACK_PYTHON="$PYTHON" PACK_STATICX="$ROOT/.venv-release/bin/staticx" \
  ./tools/finalize_release.sh dist/localflow.pyinstaller
