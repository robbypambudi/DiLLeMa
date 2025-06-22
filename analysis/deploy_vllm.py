import ray
from ray import serve
from ray.serve.llm import LLMConfig, LLMServer, LLMRouter

# Initialize Ray
llm_config = LLMConfig(
    model_loading_config=dict(
        model_id="qwen-0.5b",
        model_source="Qwen/Qwen2.5-0.5B-Instruct",
    ),
    # vision
    # model_loading_config=dict(

    deployment_config=dict(
        autoscaling_config=dict(
            min_replicas=1, max_replicas=2,
        )
    ),
    # Pass the desired accelerator type (e.g. A10G, L4, etc.)
    # accelerator_type="A10G",
    # You can customize the engine arguments (e.g. vLLM engine kwargs)
    engine_kwargs=dict(
        tensor_parallel_size=1,
        pipeline_parallel_size=2,
    ),
)

# Deploy the application
deployment = LLMServer.as_deployment(llm_config.get_serve_options(name_prefix="vLLM:")).bind(llm_config)
llm_app = LLMRouter.as_deployment().bind([deployment])
serve.run(llm_app, blocking=True)
