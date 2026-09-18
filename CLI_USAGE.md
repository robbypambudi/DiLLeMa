# CLI Usage

## Installation

Requires [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync
```

Then run CLI commands with `uv run` (for example `uv run dillema serve ...`) or `source .venv/bin/activate`.

## Single Device

Reads `LLM_MODEL` and `LLM_MODEL_SOURCE` from the repository `.env` (or `.env` in the current directory); a legacy `apps/.env` is still read for keys missing there. Starts a local Ray head if none is running. Does not start the web dashboard.

```bash
uv run dillema serve
```

Override the env model when needed:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct
```

## Multi-Node Cluster

### 1. Start Head Node

```bash
# On head node machine
dillema head
# Output: Connect workers with: dillema worker --address='192.168.1.100:6379'
```

### 2. Start Worker Nodes

```bash
# On each worker machine
dillema worker --address 192.168.1.100:6379
```

### 3. Deploy Model

```bash
# On any machine (connects to cluster)
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct \
  --ray-address ray://192.168.1.100:10001 \
  --pipeline-parallel 2
```

### 4. Stop Ray

```bash
dillema stop
```

## DiLLeMa dashboard (API + web)

From the repository (needs Node.js, `uv`, and Docker for Postgres/Qdrant):

```bash
dillema start dashboard
# same as: dillema dashboard   (add -d to run it in the background)

dillema dashboard down            # stop the API and web UI
dillema dashboard down --docker   # also stop Postgres/Qdrant (data is kept)
```

- API: http://localhost:8080
- Web: http://localhost:3000

This does not start the LLM. Run `dillema serve` separately if chat should call DiLLeMa.

## Options

- `--model-id`: Model identifier (default: `LLM_MODEL`)
- `--model-source`: HuggingFace model path (default: `LLM_MODEL_SOURCE` or `TEXT_GENERATION_MODEL`)
- `--min-replicas`: Minimum replicas (default: 1)
- `--max-replicas`: Maximum replicas (default: 1)
- `--tensor-parallel`: Tensor parallel size (default: 1)
- `--pipeline-parallel`: Pipeline parallel size (default: 1)
- `--hf-token`: HuggingFace token for gated models
- `--network-interface`: Network interface for distributed communication (e.g., eth0, enp132s0)
- `--app-host`: Application host address (default: 0.0.0.0)
- `--app-port`: Application port number (default: 8000)

## Library Usage

```python
import ray
from ray import serve
from dillema.serve import LLMServe

ray.init()

wrapper = LLMServe(
    model_id="qwen-0.5b",
    model_source="Qwen/Qwen2.5-0.5B-Instruct",
)

app = wrapper.build_app()
serve.run(app, blocking=True)
```
