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
        
        default_runtime_env = {"env_vars": {"VLLM_USE_V1": "1"}}
        if self.hf_token:
            default_runtime_env["env_vars"]["HF_TOKEN"] = self.hf_token
        if runtime_env:
            default_runtime_env.update(runtime_env)
        
        llm_config = LLMConfig(
            model_loading_config={"model_id": self.model_id, "model_source": self.model_source},
            deployment_config={"autoscaling_config": {"min_replicas": min_replicas, "max_replicas": max_replicas}},
            engine_kwargs=default_engine_kwargs,
            runtime_env=default_runtime_env,
        )
        
        self.app = build_openai_app({"llm_configs": [llm_config]})
        return self.app
