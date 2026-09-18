import os
from ray.serve.llm import LLMConfig, build_openai_app


class LLMServe:
    """Wrapper for Ray Serve LLM deployment"""
    def __init__(self, model_id: str, model_source: str, hf_token: str = None, 
                 tensor_parallel_size: int = 1, pipeline_parallel_size: int = 1):
        self.model_id = model_id
        self.model_source = model_source
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.tensor_parallel_size = tensor_parallel_size
        self.pipeline_parallel_size = pipeline_parallel_size
        self.app = None

    def _worker_runtime_env(self, runtime_env: dict | None) -> dict:
        """Runtime env shared by the replica and the engine workers it starts.

        No `py_executable`: on a multi-node cluster the driver's interpreter
        path does not exist on the other nodes, and each node's raylet already
        runs the Python `dillema head`/`dillema worker` was started with.
        (`dillema serve` disables Ray's `uv run` propagation instead.)
        """
        merged = {
            "env_vars": {"VLLM_USE_V1": "1"},
            # Child actors (EngineCore, GPU workers) inherit this runtime env,
            # so the hook reaches the processes that launch Triton kernels.
            "worker_process_setup_hook": "dillema.serve.triton_allocator.install",
        }
        if self.hf_token:
            merged["env_vars"]["HF_TOKEN"] = self.hf_token
        if runtime_env:
            extra_vars = runtime_env.get("env_vars") or {}
            merged["env_vars"].update(extra_vars)
            for key, value in runtime_env.items():
                if key != "env_vars":
                    merged[key] = value
        return merged

    def build_app(self, min_replicas: int = 1, max_replicas: int = 1, 
                  engine_kwargs: dict = None, runtime_env: dict = None):
        """Build OpenAI-compatible app"""
        default_engine_kwargs = {
            "tensor_parallel_size": self.tensor_parallel_size,
            "pipeline_parallel_size": self.pipeline_parallel_size,
            "trust_remote_code": True,
        }
        if engine_kwargs:
            default_engine_kwargs.update(engine_kwargs)

        default_runtime_env = self._worker_runtime_env(runtime_env)
        
        llm_config = LLMConfig(
            model_loading_config={"model_id": self.model_id, "model_source": self.model_source},
            deployment_config={"autoscaling_config": {"min_replicas": min_replicas, "max_replicas": max_replicas}},
            engine_kwargs=default_engine_kwargs,
            runtime_env=default_runtime_env,
        )
        
        self.app = build_openai_app({"llm_configs": [llm_config]})
        return self.app
