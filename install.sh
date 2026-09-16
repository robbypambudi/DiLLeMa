#!/bin/bash
# Hentikan script jika terjadi error
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Memastikan uv terinstal ==="
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="${HOME}/.local/bin:${PATH}"
fi
uv --version

echo "=== Menginstal Python 3.12.9 dan dependensi proyek ==="
uv python install 3.12.9
uv sync --group dev

echo "=== Verifikasi instalasi ==="
uv run python --version
uv run python -c "import dillema; print('DiLLeMa', dillema.__version__)"

echo "=== Instalasi selesai ==="
echo "Jalankan perintah dengan: uv run dillema --help"
echo "Atau aktifkan environment: source .venv/bin/activate"
