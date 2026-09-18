import pytest

# LLMServe imports ray.serve.llm at module load, so skip the whole module
# when the serving stack isn't installed (e.g. a local macOS dev machine).
# It runs for real in CI where ray is installed.
pytest.importorskip("ray.serve.llm")

from dillema.serve import LLMServe


def test_defaults():
    s = LLMServe(model_id="qwen", model_source="Qwen/Qwen2.5-0.5B-Instruct")
    assert s.model_id == "qwen"
    assert s.tensor_parallel_size == 1
    assert s.pipeline_parallel_size == 1
    assert s.app is None


def test_hf_token_explicit_takes_precedence(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "env-token")
    s = LLMServe(model_id="m", model_source="src", hf_token="explicit-token")
    assert s.hf_token == "explicit-token"


def test_hf_token_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "env-token")
    s = LLMServe(model_id="m", model_source="src")
    assert s.hf_token == "env-token"


def test_worker_runtime_env_does_not_pin_the_driver_python():
    s = LLMServe(model_id="m", model_source="src", hf_token="tok")
    env = s._worker_runtime_env({"env_vars": {"GLOO_SOCKET_IFNAME": "eth0"}})
    # The driver's interpreter path does not exist on other nodes.
    assert "py_executable" not in env
    assert env["env_vars"]["VLLM_USE_V1"] == "1"
    assert env["env_vars"]["HF_TOKEN"] == "tok"
    assert env["env_vars"]["GLOO_SOCKET_IFNAME"] == "eth0"


def test_workers_get_the_triton_allocator_hook():
    s = LLMServe(model_id="m", model_source="src")
    env = s._worker_runtime_env(None)
    assert env["worker_process_setup_hook"] == "dillema.serve.triton_allocator.install"


def test_tma_kernels_run_off_the_main_thread_once_installed():
    import threading

    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("needs a CUDA GPU")
    from vllm.model_executor.layers.fla.ops.solve_tril import solve_tril

    from dillema.serve.triton_allocator import install

    install()
    errors = []

    def run():
        # Ray's compiled DAG runs the model in a thread of its own; Triton's
        # allocator ContextVar does not follow it there.
        try:
            a = torch.randn(1, 64, 4, 64, device="cuda").tril(-1) * 0.01
            solve_tril(a)
            torch.cuda.synchronize()
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert not errors, errors
