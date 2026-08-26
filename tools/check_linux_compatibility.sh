#!/usr/bin/env bash
# 验证最终 Linux 制品的静态结构、原生启动与声明的 x86-64-v1 CPU 下限。
set -euo pipefail

BINARY="${1:-dist/localflow}"
test -x "$BINARY" || { echo "release binary is missing: $BINARY" >&2; exit 1; }
command -v file >/dev/null || { echo "file is required" >&2; exit 1; }
command -v qemu-x86_64 >/dev/null || { echo "qemu-user is required" >&2; exit 1; }

file "$BINARY" | grep -q 'ELF 64-bit.*x86-64'
LDD_OUTPUT="$(ldd "$BINARY" 2>&1 || true)"
grep -q 'not a dynamic executable' <<<"$LDD_OUTPUT"
timeout 60 "$BINARY" --help >/dev/null

# qemu64、Core 2、第一代 Opteron 覆盖不含 AVX 的早期 x86-64 CPU。
for cpu in qemu64 core2duo Opteron_G1; do
  echo "compatibility smoke: $cpu"
  timeout 90 qemu-x86_64 -cpu "$cpu" "$BINARY" --help >/dev/null
done
