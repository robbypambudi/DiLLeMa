#!/bin/bash
# Hentikan script jika terjadi error
set -e

echo "=== Memperbarui sistem dan menginstal dependensi sistem ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y wget curl build-essential libssl-dev zlib1g-dev \
    libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev \
    libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev tk-dev

echo "=== Mengunduh dan menginstal Miniconda ==="
cd /tmp
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p $HOME/miniconda
export PATH="$HOME/miniconda/bin:$PATH"
echo 'export PATH="$HOME/miniconda/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

echo "=== Memastikan conda tersedia ==="
conda --version

echo "=== Membuat environment Conda dengan Python 3.12.0 ==="
conda create -y -n ray_env python=3.12.9

echo "=== Mengaktifkan environment ==="
source $HOME/miniconda/bin/activate ray_env

echo "=== Menginstal Astral UV untuk manajemen paket yang lebih cepat ==="
pip install -U pip
pip install uv

echo "=== Memasang Ray dengan fitur Serve dan vLLM menggunakan UV ==="
# Menggunakan UV untuk instalasi yang lebih cepat
uv pip install ray "ray[serve, llm]>=2.43.0" "vllm>=0.7.2"

echo "=== Verifikasi instalasi ==="
python --version
ray --version
python -c "import ray; import vllm; print('✅ Ray dan vLLM berhasil diimpor.')"

echo "=== Instalasi selesai. Gunakan environment dengan: ==="
echo "conda activate ray_env"
echo ""
echo "📦 Paket yang terinstal:"
echo "- Ray dengan fitur Serve"
echo "- vLLM untuk inferensi LLM yang cepat"
echo "- UV untuk manajemen paket yang efisien"