from pathlib import Path
import os

from dillema.env import apply_env_file, model_id_from_env, model_source_from_env


def test_apply_env_file_does_not_override_existing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "already-set")
    monkeypatch.delenv("LLM_MODEL_SOURCE", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_MODEL=qwen-7b\n" 'LLM_MODEL_SOURCE="Qwen/Qwen2.5-0.5B-Instruct"\n',
        encoding="utf-8",
    )
    apply_env_file(env_file)
    assert os.environ["LLM_MODEL"] == "already-set"
    assert os.environ["LLM_MODEL_SOURCE"] == "Qwen/Qwen2.5-0.5B-Instruct"


def test_model_lookups_prefer_llm_model_source(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen-7b")
    monkeypatch.setenv("LLM_MODEL_SOURCE", "Qwen/Qwen2.5-0.5B-Instruct")
    monkeypatch.setenv("TEXT_GENERATION_MODEL", "other/model")
    assert model_id_from_env() == "qwen-7b"
    assert model_source_from_env() == "Qwen/Qwen2.5-0.5B-Instruct"


def test_model_source_falls_back_to_text_generation_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SOURCE", raising=False)
    monkeypatch.delenv("DILLEMA_MODEL_SOURCE", raising=False)
    monkeypatch.setenv("TEXT_GENERATION_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    assert model_source_from_env() == "Qwen/Qwen2.5-0.5B-Instruct"


def test_load_dillema_env_disables_uv_run_workers(monkeypatch):
    from dillema.env import load_dillema_env

    monkeypatch.delenv("RAY_ENABLE_UV_RUN_RUNTIME_ENV", raising=False)
    load_dillema_env()
    assert os.environ["RAY_ENABLE_UV_RUN_RUNTIME_ENV"] == "0"


def test_repository_env_is_read_before_the_legacy_apps_env(tmp_path, monkeypatch):
    from dillema import env

    repo = tmp_path / "repo"
    (repo / "dillema").mkdir(parents=True)
    (repo / "apps").mkdir()
    (repo / ".env").write_text("LLM_MODEL=from-root\n", encoding="utf-8")
    (repo / "apps" / ".env").write_text(
        "LLM_MODEL=from-apps\nLLM_MODEL_SOURCE=legacy/only\n", encoding="utf-8"
    )
    monkeypatch.setattr(env, "__file__", str(repo / "dillema" / "env.py"))
    monkeypatch.chdir(tmp_path)
    for key in ("LLM_MODEL", "LLM_MODEL_SOURCE"):
        monkeypatch.delenv(key, raising=False)

    env.load_dillema_env()

    assert os.environ["LLM_MODEL"] == "from-root"
    # A key only the old file still holds keeps working until it is moved.
    assert os.environ["LLM_MODEL_SOURCE"] == "legacy/only"
