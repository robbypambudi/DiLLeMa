# DiLLeMa

DiLLeMa is a distributed Large Language Model (LLM) serving system that provides an easy-to-use interface for deploying and using LLMs in distributed settings. Built on top of Ray Framework and VLLM, it enables efficient multi-GPU and multi-node deployments.

![Architecture](https://raw.githubusercontent.com/robbypambudi/DiLLeMa/refs/heads/main/docs/assets/architecture.png)

## Features

- **Distributed LLM Serving**: Deploy LLMs across multiple GPUs and nodes using Ray and VLLM
- **Simple CLI Interface**: Easy-to-use command-line interface for managing Ray clusters and deploying models
- **OpenAI-Compatible API**: Standard OpenAI-compatible API endpoints for seamless integration
- **Tensor and Pipeline Parallelism**: Support for both tensor and pipeline parallelism for large models
- **Auto-scaling**: Automatic scaling of model replicas based on demand
- **Web UI**: FastAPI-based web interface for managing deployments

## Installation

### From PyPI

```bash
pip install dillema
```

### From Source

```bash
git clone https://github.com/robbypambudi/DiLLeMa.git
cd DiLLeMa
pip install -e .
```

### Prerequisites

- Python 3.12.9
- CUDA-capable GPU(s) (for GPU acceleration)
- Ray 2.50.0
- VLLM >= 0.11.0

> **Note**: For safety, it's recommended to use a conda environment:
> ```bash
> conda create -n dillema python=3.12.9
> conda activate dillema
> ```

## Project Structure

```
DiLLeMa/
│
├── dillema/                    # Main package
│   ├── cli.py                  # CLI interface (head, worker, serve, stop commands)
│   ├── serve/                  # LLM serving module
│   │   └── llm.py              # Ray Serve LLM wrapper
│   ├── ray/                    # Ray utilities
│   │   └── main.py             # Ray container and connection management
│   └── app/                    # Web UI application
│       ├── main.py             # FastAPI web interface
│       └── templates/          # HTML templates
│
├── evaluation/                 # Evaluation scripts and tools
├── analysis/                  # Analysis notebooks and scripts
├── docs/                      # Documentation and assets
├── test/                      # Unit tests
├── pyproject.toml             # Project configuration
└── requirements.txt           # Python dependencies
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

### Single Device Deployment

Deploy a model on a single machine:

```bash
dillema serve \
  --model-id qwen-0.5b \
  --model-source Qwen/Qwen2.5-0.5B-Instruct
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
- `--model-id`: Model identifier (required)
- `--model-source`: HuggingFace model path (required)
- `--min-replicas`: Minimum replicas (default: 1)
- `--max-replicas`: Maximum replicas (default: 1)
- `--tensor-parallel`: Tensor parallel size (default: 1)
- `--pipeline-parallel`: Pipeline parallel size (default: 1)
- `--hf-token`: HuggingFace token for gated models
- `--ray-address`: Ray cluster address (default: auto)
- `--network-interface`: Network interface for distributed communication (e.g., eth0, enp132s0)
- `--app-host`: Application host address (default: 0.0.0.0)
- `--app-port`: Application port number (default: 8000)

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
