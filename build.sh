#!/bin/bash

# Pastikan script dijalankan di dalam folder proyek yang sesuai
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

# Nama package yang ingin diperiksa dan diinstal (ganti sesuai dengan nama package Anda)
PACKAGE_NAME="dillema"

# Mengecek apakah package sudah terinstal
if pip show "$PACKAGE_NAME" > /dev/null 2>&1; then
    echo "Package $PACKAGE_NAME ditemukan. Meng-uninstall terlebih dahulu..."
    
    # Uninstall package yang sudah terinstal
    pip uninstall -y "$PACKAGE_NAME"
    
    # Mengecek jika uninstall berhasil
    if [ $? -eq 0 ]; then
        echo "$PACKAGE_NAME berhasil di-uninstall."
    else
        echo "Gagal meng-uninstall $PACKAGE_NAME."
        exit 1
    fi
else
    echo "Package $PACKAGE_NAME tidak ditemukan. Melanjutkan ke build dan install."
fi

# Membuat direktori dist jika belum ada
echo "Mempersiapkan build..."
mkdir -p dist

# Membuild paket menggunakan python -m build
echo "Membangun paket..."
python -m build

# Memastikan bahwa build berhasil
if [ $? -eq 0 ]; then
    echo "Build berhasil! Menginstal paket..."

    # Menginstal paket lokal menggunakan pip
    pip install dist/*

    # Memastikan install berhasil
    if [ $? -eq 0 ]; then
        echo "Paket berhasil diinstal."
    else
        echo "Gagal menginstal paket."
        exit 1
    fi
else
    echo "Build gagal."
    exit 1
fi
