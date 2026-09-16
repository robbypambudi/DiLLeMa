#!/bin/bash
set -euo pipefail

# Pastikan script dijalankan di dalam folder proyek yang sesuai
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

PACKAGE_NAME="dillema"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv tidak ditemukan. Instal uv: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Mengecek apakah package sudah terinstal di environment proyek
if uv pip show "$PACKAGE_NAME" > /dev/null 2>&1; then
    echo "Package $PACKAGE_NAME ditemukan. Meng-uninstall terlebih dahulu..."
    uv pip uninstall "$PACKAGE_NAME"
    echo "$PACKAGE_NAME berhasil di-uninstall."
else
    echo "Package $PACKAGE_NAME tidak ditemukan. Melanjutkan ke build dan install."
fi

echo "Mempersiapkan build..."
rm -rf dist
mkdir -p dist

echo "Membangun paket..."
uv build

echo "Build berhasil! Menginstal paket..."
uv pip install dist/*.whl
echo "Paket berhasil diinstal."
