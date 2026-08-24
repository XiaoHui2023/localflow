#!/usr/bin/env bash
# 构建新前端、PyInstaller onefile，并在 Linux 上强制转换为 staticx 单文件。
# PACK_SKIP_FRONTEND_BUILD=1 仅供 CI 在宿主机已完成 npm ci/build 后使用。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BOOTSTRAP="${PACK_PYTHON:-python3}"
if [[ ! -x "$ROOT/.venv-release/bin/python" ]]; then
  rm -rf "$ROOT/.venv-release"
  "$PYTHON_BOOTSTRAP" -m venv "$ROOT/.venv-release"
fi
PYTHON="$ROOT/.venv-release/bin/python"

if [[ "${PACK_SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
  npm --prefix frontend ci
  npm --prefix frontend run build
fi
test -f frontend/dist/index.html || { echo "frontend/dist/index.html is missing" >&2; exit 1; }

if [[ "${PACK_SKIP_PYTHON_INSTALL:-0}" != "1" ]]; then
  "$PYTHON" -m pip install --upgrade pip setuptools wheel
  "$PYTHON" -m pip install --upgrade --force-reinstall . "pyinstaller>=6,<7" "staticx>=0.14,<1"
fi
command -v patchelf >/dev/null || { echo "patchelf is required by staticx" >&2; exit 1; }

rm -rf build dist
"$PYTHON" -m PyInstaller --clean --noconfirm app.spec
test -x dist/localflow || { echo "PyInstaller did not produce dist/localflow" >&2; exit 1; }

STATICX="$ROOT/.venv-release/bin/staticx"
# 默认压缩形式在 Xenial 实测启动 SIGSEGV；兼容发布固定使用官方无压缩模式。
"$STATICX" --no-compress dist/localflow dist/localflow.staticx
mv dist/localflow.staticx dist/localflow
chmod 0755 dist/localflow

VERSION="$($PYTHON -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
BUNDLE="localflow-${VERSION}-linux-x86_64"
mkdir -p "dist/$BUNDLE/deploy" "dist/$BUNDLE/docs"
install -m 0755 dist/localflow "dist/$BUNDLE/localflow"
install -m 0644 README.md "dist/$BUNDLE/README.md"
install -m 0644 deploy/localflow-static.service "dist/$BUNDLE/deploy/localflow.service"
install -m 0644 deploy/localflow.tmpfiles.conf "dist/$BUNDLE/deploy/localflow.tmpfiles.conf"
install -m 0755 deploy/localflow-set-time.py "dist/$BUNDLE/deploy/localflow-set-time.py"
install -m 0644 deploy/localflow.sudoers "dist/$BUNDLE/deploy/localflow.sudoers"
install -m 0644 docs/operations.md "dist/$BUNDLE/docs/operations.md"
tar -C dist -czf "dist/$BUNDLE.tar.gz" "$BUNDLE"
rm -rf "dist/$BUNDLE"
(cd dist && sha256sum localflow "$BUNDLE.tar.gz" > SHA256SUMS)

file dist/localflow
LDD_OUTPUT="$(ldd dist/localflow 2>&1 || true)"
if ! grep -q 'not a dynamic executable' <<<"$LDD_OUTPUT"; then
  echo "staticx structural audit failed: final executable is dynamically linked" >&2
  echo "$LDD_OUTPUT" >&2
  exit 1
fi
echo "release assets: dist/localflow, dist/$BUNDLE.tar.gz, dist/SHA256SUMS"
