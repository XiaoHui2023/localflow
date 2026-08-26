#!/usr/bin/env bash
# 在 PyInstaller 构建基线内完成 StaticX 封装并生成发布资产。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INPUT="${1:-dist/localflow.pyinstaller}"
STATICX="${PACK_STATICX:-staticx}"
test -x "$INPUT" || { echo "PyInstaller input is missing: $INPUT" >&2; exit 1; }
[[ "$INPUT" != "dist/localflow" ]] || { echo "StaticX input must not overwrite its source path" >&2; exit 1; }
command -v "$STATICX" >/dev/null || { echo "staticx is required" >&2; exit 1; }
command -v patchelf >/dev/null || { echo "patchelf is required by staticx" >&2; exit 1; }

OBJCOPY_VERSION="$(objcopy --version | head -n 1)"
echo "finalizing with $OBJCOPY_VERSION"
# StaticX 官方问题 #205：旧 objcopy 不能处理由较新系统预编译的 bootloader。
# 旧基线发布必须从源码构建 StaticX，使 bootloader 与本机工具链同源；wheel 仍要求新 objcopy。
OBJCOPY_MINOR="$(objcopy --version | sed -n '1s/.* \([0-9][0-9]*\)\.\([0-9][0-9]*\).*/\1 \2/p')"
read -r OBJCOPY_MAJOR OBJCOPY_PATCH <<<"$OBJCOPY_MINOR"
if [[ "${PACK_STATICX_SOURCE_BUILD:-0}" != "1" ]] && \
   (( OBJCOPY_MAJOR < 2 || (OBJCOPY_MAJOR == 2 && OBJCOPY_PATCH < 35) )); then
  echo "binutils 2.35+ is required to avoid corrupting the staticx bootloader" >&2
  exit 1
fi

rm -f dist/localflow dist/localflow.staticx
# 固定无压缩模式，减少启动阶段变量；最终体积由外层 tar.gz 压缩。
"$STATICX" --no-compress "$INPUT" dist/localflow.staticx
mv dist/localflow.staticx dist/localflow
chmod 0755 dist/localflow

METADATA_PYTHON="${PACK_PYTHON:-python3}"
VERSION="$("$METADATA_PYTHON" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
BUNDLE="localflow-${VERSION}-linux-x86_64"
rm -rf "dist/$BUNDLE" "dist/$BUNDLE.tar.gz" dist/SHA256SUMS
mkdir -p "dist/$BUNDLE/deploy" "dist/$BUNDLE/docs" "dist/$BUNDLE/skills" \
  "dist/$BUNDLE/config/tasks" "dist/$BUNDLE/config/shared" "dist/$BUNDLE/scripts" "dist/$BUNDLE/plugins" \
  "dist/$BUNDLE/runtime/instances" "dist/$BUNDLE/logs" "dist/$BUNDLE/secrets" \
  "dist/$BUNDLE/exports"
install -m 0755 dist/localflow "dist/$BUNDLE/localflow"
install -m 0644 README.md "dist/$BUNDLE/README.md"
install -m 0644 deploy/localflow-static.service "dist/$BUNDLE/deploy/localflow.service"
install -m 0644 deploy/localflow.tmpfiles.conf "dist/$BUNDLE/deploy/localflow.tmpfiles.conf"
install -m 0755 deploy/localflow-set-time.py "dist/$BUNDLE/deploy/localflow-set-time.py"
install -m 0644 deploy/localflow.sudoers "dist/$BUNDLE/deploy/localflow.sudoers"
install -m 0644 docs/api.md docs/configuration.md docs/operations.md docs/plugins.md \
  docs/security.md docs/stopping.md docs/terminal.md "dist/$BUNDLE/docs/"
cp -R skills/. "dist/$BUNDLE/skills/"
install -m 0644 src/localflow/starter_root/config/tasks/*.yaml "dist/$BUNDLE/config/tasks/"
install -m 0644 src/localflow/starter_root/config/shared/*.yaml "dist/$BUNDLE/config/shared/"
install -m 0755 src/localflow/starter_root/scripts/*.py "dist/$BUNDLE/scripts/"
install -m 0644 src/localflow/builtin_plugins/declarative.py.example "dist/$BUNDLE/plugins/declarative.py"
install -m 0644 src/localflow/builtin_plugins/verification.py.example "dist/$BUNDLE/plugins/verification.py"
install -m 0644 src/localflow/builtin_plugins/interactive.py.example "dist/$BUNDLE/plugins/interactive.py"
install -m 0644 src/localflow/builtin_plugins/marker.py.example "dist/$BUNDLE/plugins/marker.py"
install -m 0644 src/localflow/builtin_plugins/README.md.example "dist/$BUNDLE/plugins/README.md"
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
