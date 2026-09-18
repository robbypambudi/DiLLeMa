# DiLLeMa

DiLLeMa is a distributed Large Language Model (LLM) serving system that provides an easy-to-use interface for deploying and using LLMs in distributed settings. Built on top of Ray Framework and VLLM, it enables efficient multi-GPU and multi-node deployments.

![Architecture](https://raw.githubusercontent.com/robbypambudi/DiLLeMa/refs/heads/main/docs/assets/architecture.png)

## Features

An opt-in Knowledge Graph pilot for DiLLeMa v2 is available in `apps/`. See the
[implementation plan and agent handoff](docs/DILLEMA_V2_PLAN.md),
[setup/runbook](docs/DILLEMA_V2_RUNBOOK.md),
[validation findings](docs/DILLEMA_V2_VALIDATION.md), and
[target architecture](docs/DILLEMA_V2_DESIGN.md).

- **Distributed LLM Serving**: Deploy LLMs across multiple GPUs and nodes using Ray and VLLM
- **Simple CLI Interface**: Easy-to-use command-line interface for managing Ray clusters and deploying models
- **OpenAI-Compatible API**: Standard OpenAI-compatible API endpoints for seamless integration
- **Tensor and Pipeline Parallelism**: Support for both tensor and pipeline parallelism for large models
- **Auto-scaling**: Automatic scaling of model replicas based on demand

## Installation

Requires [uv](https://docs.astral.sh/uv/).

### From PyPI

```bash
uv pip install dillema
```

### From Source

```bash
git clone https://github.com/robbypambudi/DiLLeMa.git
cd DiLLeMa
uv sync
```

Or run `./install.sh` to install uv (if missing), pin Python 3.12.9, and sync the environment.

After that, run commands with `uv run` (for example `uv run dillema --help`) or activate `.venv`:

```bash
source .venv/bin/activate
```

### With Docker

Build the GPU serving image (based on `rayproject/ray:2.55.0-py312-cu128`):

```bash
docker build -t dillema:2.55.0 .
docker run --gpus all --rm -it dillema:2.55.0 bash -lc \
  'ray start --head && dillema serve --model-id qwen-3.5-0.8b \
     --model-source Qwen/Qwen3.5-0.8B'
```

Requires the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). See the header comment in the `Dockerfile` and `deploy/auth-proxy/` for securing the endpoint.

### Prerequisites

- Python 3.12.9
- CUDA-capable GPU(s) (for GPU acceleration)
- Ray 2.55.0
- VLLM 0.18.0

> **Note**: `uv sync` creates `.venv` with Python 3.12.9 (see `.python-version`). You do not need conda.

## Project Structure

```
DiLLeMa/
│
├── dillema/                    # Main package
│   ├── cli.py                  # CLI interface (head, worker, serve, stop commands)
│   └── serve/                  # LLM serving module
│       └── llm.py              # Ray Serve LLM wrapper
│
├── deploy/                     # Deployment helpers (e.g. auth-proxy for the endpoint)
├── evaluation/                 # Evaluation scripts and tools
├── analysis/                  # Analysis notebooks and scripts
├── docs/                      # Documentation and assets
├── test/                      # Unit tests
├── pyproject.toml             # Project configuration
└── uv.lock                    # Locked dependency versions
```

## Flow Diagram

```
  +------------------------+
  |      User/Client        |
  +------------------------+
            |
            v
  +------------------------+     +------------------------+
  |   API Server (Ray Serve)|<--->|   Ray Head Node        |
  |   OpenAI-Compatible API |     |   (Ray Management)     |
  +------------------------+     +------------------------+
            |                         ^
            v                         |
    +--------------------+    +--------------------+
    |  Ray Cluster       |----|  Ray Worker Nodes  |
    |  (Distributed)     |    |  (GPU Workers)     |
    +--------------------+    +--------------------+
            |
            v
  +------------------------+
  |  VLLM Engine           |
  |  (Model Inference)     |
  +------------------------+
            |
            v
  +------------------------+
  |  LLM Model             |
  |  (HuggingFace)         |
  +------------------------+
```

## Usage

If `.venv` is not activated, prefix commands with `uv run` (for example `uv run dillema serve ...`).

### Single Device Deployment

`dillema serve` reads `LLM_MODEL` and `LLM_MODEL_SOURCE` from `apps/.env` and starts a local Ray head if needed. The web dashboard is a separate command (`dillema dashboard`).

```bash
uv run dillema serve
```

Add `-d` (or `--detach`) to return to the terminal immediately and keep running
in the background, including after the terminal closes:

```bash
uv run dillema serve -d
uv run dillema dashboard -d
# Equivalent dashboard command:
uv run dillema start dashboard -d
```

Each command prints its background PID and a `tail -f` command for its log in
`$XDG_STATE_HOME/dillema` (default: `~/.local/state/dillema`). Startup continues
asynchronously; check the log for readiness or errors. Use `kill <PID>` to stop
the background process; for the dashboard this also stops the API/web processes
it started. Use `dillema stop` to stop the Ray cluster and deployed model.
Without `-d`, commands continue running in the foreground.

Or pass the model explicitly:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-1.5B-Instruct
```

### Multi-Node Cluster Deployment

#### 1. Start Head Node

On the head node machine:

```bash
dillema head
# Output: Connect workers with: dillema worker --address='192.168.1.100:6379'
# Dashboard: http://192.168.1.100:8265
```

#### 2. Start Worker Nodes

On each worker machine:

```bash
dillema worker --address 192.168.1.100:6379
```

#### 3. Deploy Model

On any machine connected to the cluster:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct \
  --ray-address ray://192.168.1.100:10001 \
  --tensor-parallel 2 \
  --pipeline-parallel 2
```

#### 4. Stop Ray Cluster

```bash
dillema stop
```

### Command Options

#### `dillema head`
- `--port`: Ray port (default: 6379)
- `--dashboard-host`: Dashboard host (default: 0.0.0.0)

#### `dillema worker`
- `--address`: Head node address in format `ip:port` (required)

#### `dillema serve`
- `-d`, `--detach`: Run in the background with output saved to a log
- `--model-id`: Model identifier (default: `LLM_MODEL` in `apps/.env`)
- `--model-source`: HuggingFace model path (default: `LLM_MODEL_SOURCE` or `TEXT_GENERATION_MODEL`)
- `--min-replicas`: Minimum replicas (default: 1)
- `--max-replicas`: Maximum replicas (default: 1)
- `--tensor-parallel`: Tensor parallel size (default: 1)
- `--pipeline-parallel`: Pipeline parallel size (default: 1)
- `--hf-token`: HuggingFace token for gated models
- `--ray-address`: Ray cluster address (default: auto)
- `--network-interface`: Network interface for distributed communication (e.g., eth0, enp132s0)
- `--app-host`: Application host address (default: 0.0.0.0)
- `--app-port`: Application port number (default: 8000)

#### `dillema dashboard` / `dillema start dashboard`
- `-d`, `--detach`: Run the API and web UI in the background with output saved to a log
- `--api-host`: API host (default: 0.0.0.0)
- `--api-port`: API port (default: 8080)
- `--web-port`: Web UI port (default: 3000)
- `--no-docker`: Skip starting Postgres/Qdrant with Docker Compose

### Python API Usage

You can also use DiLLeMa programmatically:

```python
import ray
from ray import serve
from dillema.serve import LLMServe

ray.init()

wrapper = LLMServe(
    model_id="qwen-0.5b",
    model_source="Qwen/Qwen2.5-0.5B-Instruct",
    tensor_parallel_size=2,
    pipeline_parallel_size=1,
)

app = wrapper.build_app(
    min_replicas=1,
    max_replicas=2
)

serve.run(app, blocking=True)
```

## Architecture

DiLLeMa leverages Ray as the distributed orchestration framework and VLLM as the inference engine:

- **Ray**: Manages distributed resources, task scheduling, autoscaling, and fault tolerance
- **VLLM**: Optimizes LLM inference through dynamic batching, kernel fusion, and advanced memory management
- **Ray Serve**: Provides the serving layer with OpenAI-compatible API endpoints

The system supports three deployment configurations:
- **Single GPU**: Deploy models on a single GPU
- **Multi-GPU**: Deploy models across multiple GPUs using tensor parallelism
- **Multi-node Multi-GPU**: Deploy models across multiple nodes and GPUs using pipeline parallelism

## Documentation

For detailed documentation, see [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)

For CLI usage examples, see [CLI_USAGE.md](CLI_USAGE.md)

## License

MIT License - see [LICENSE](LICENSE) file for details

## Authors

- Robby Ulung Pambudi (robby.pambudi10@gmail.com)
