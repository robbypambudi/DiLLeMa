import os
from pathlib import Path


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def apply_env_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        parsed = _parse_env_line(raw)
        if parsed is None:
            continue
        key, value = parsed
        os.environ.setdefault(key, value)


def env_file_candidates() -> list[Path]:
    repo = Path(__file__).resolve().parents[1]
    cwd = Path.cwd()
    ordered = [
        cwd / ".env",
        cwd / "apps" / ".env",
        repo / ".env",
        repo / "apps" / ".env",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    for path in ordered:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        files.append(resolved)
    return files


def load_dillema_env() -> None:
    for path in env_file_candidates():
        apply_env_file(path)
    # `uv run dillema serve` would otherwise make Ray workers run `uv run` in a
    # packaged working_dir without .venv, so they re-download torch/vLLM.
    os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")


def model_id_from_env() -> str | None:
    for key in ("LLM_MODEL", "DILLEMA_MODEL_ID"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None


def model_source_from_env() -> str | None:
    for key in ("LLM_MODEL_SOURCE", "TEXT_GENERATION_MODEL", "DILLEMA_MODEL_SOURCE"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return None
