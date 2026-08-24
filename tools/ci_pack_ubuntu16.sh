#!/usr/bin/env bash
# 在 Ubuntu 16.04/glibc 2.23 基线上固定 Python 3.11 构建发布包。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends ca-certificates wget bzip2 binutils patchelf file build-essential
rm -rf /var/lib/apt/lists/*

CONDA_INSTALLER=Miniconda3-py311_23.5.2-0-Linux-x86_64.sh
CONDA_ROOT="${PACK_CONDA_ROOT:-$PWD/.release-conda}"
if [[ ! -x "$CONDA_ROOT/bin/python" ]]; then
  wget --tries=3 --timeout=30 "https://repo.anaconda.com/miniconda/$CONDA_INSTALLER" -O "/tmp/$CONDA_INSTALLER"
  bash "/tmp/$CONDA_INSTALLER" -b -p "$CONDA_ROOT"
  rm -f "/tmp/$CONDA_INSTALLER"
fi

rm -rf .venv-release build dist
PACK_PYTHON="$CONDA_ROOT/bin/python" PACK_SKIP_FRONTEND_BUILD=1 PACK_DEFER_STATICX=1 ./tools/pack.sh
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" build dist .venv-release
