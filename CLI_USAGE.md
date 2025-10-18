# CLI Usage

## Installation

```bash
pip install -e .
```

## Single Device

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

## Options

- `--model-id`: Model identifier (required)
- `--model-source`: HuggingFace model path (required)
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
