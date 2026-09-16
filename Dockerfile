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

WORKDIR /home/ray/dillema

# vLLM is not in the base ray image (only ray-llm bundles it, and that variant
# has no py312 build for 2.50.0). Install it explicitly, matching pyproject.
RUN pip install --no-cache-dir "vllm>=0.11.0"

# Install DiLLeMa. pyproject pins requires-python == 3.12.9; the base image ships
# 3.12.x, so skip the strict interpreter check (patch differences are harmless).
COPY --chown=ray:users . .
RUN pip install --no-cache-dir --ignore-requires-python -e .

# OpenAI-compatible API (bind to localhost in prod, front with an auth proxy).
EXPOSE 8000
# Ray dashboard.
EXPOSE 8265

ENTRYPOINT ["dillema"]
CMD ["--help"]
