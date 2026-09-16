#!/bin/bash
# Backward-compatible wrapper. Environment setup is now uv-based (no conda).
set -euo pipefail
exec "$(dirname "$0")/install.sh"
