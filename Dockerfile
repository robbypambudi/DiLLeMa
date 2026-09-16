# DiLLeMa serving image.
#
# Base: official Ray 2.50.0 image with Python 3.12 + CUDA 12.8 (x86_64).
# Verified to exist as rayproject/ray:2.50.0-py312-cu128. The GPU is provided by
# the host at run time, so build works anywhere but running needs the NVIDIA
# Container Toolkit and `--gpus all`.
#
# Build:
#   docker build -t dillema:2.50.0 .
# Run (single node — start the cluster, then serve):
#   docker run --gpus all --rm -it dillema:2.50.0 bash -lc \
#     'ray start --head && dillema serve --model-id qwen-0.5b \
#        --model-source Qwen/Qwen2.5-0.5B-Instruct \
#        --app-host 127.0.0.1 --app-port 8001'
# (Front the endpoint with deploy/auth-proxy/ for authentication.)
FROM rayproject/ray:2.50.0-py312-cu128

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /home/ray/dillema

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies first so the layer caches independently of source changes.
# uv installs CPython 3.12.9 to match requires-python; CUDA libs come from the base image.
COPY --chown=ray:users pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Install DiLLeMa (vLLM comes from the lockfile / project dependencies).
COPY --chown=ray:users . .
RUN uv sync --frozen --no-dev

ENV PATH="/home/ray/dillema/.venv/bin:$PATH"

# OpenAI-compatible API (bind to localhost in prod, front with an auth proxy).
EXPOSE 8000
# Ray dashboard.
EXPOSE 8265

ENTRYPOINT ["dillema"]
CMD ["--help"]
