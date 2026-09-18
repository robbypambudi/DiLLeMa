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


def test_worker_runtime_env_uses_current_python():
    import sys

    s = LLMServe(model_id="m", model_source="src", hf_token="tok")
    env = s._worker_runtime_env({"env_vars": {"GLOO_SOCKET_IFNAME": "eth0"}})
    assert env["py_executable"] == sys.executable
    assert env["env_vars"]["VLLM_USE_V1"] == "1"
    assert env["env_vars"]["HF_TOKEN"] == "tok"
    assert env["env_vars"]["GLOO_SOCKET_IFNAME"] == "eth0"
