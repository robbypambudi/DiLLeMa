import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def find_dashboard() -> Path:
    env = os.environ.get("DILLEMA_DASHBOARD") or os.environ.get("DILLEMA_RAGFORGE")
    if env:
        root = Path(env).expanduser().resolve()
        if (root / "app" / "main.py").is_file():
            return root
        sys.exit(f"{env} is not a DiLLeMa dashboard tree (missing app/main.py)")

    candidates = [
        Path(__file__).resolve().parents[1] / "apps",
        Path.cwd() / "apps",
    ]
    for root in candidates:
        if (root / "app" / "main.py").is_file():
            return root
    sys.exit(
        "DiLLeMa dashboard not found. Run this from the DiLLeMa repository "
        "or set DILLEMA_DASHBOARD to apps/."
    )


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def _ensure_docker(root: Path) -> None:
    compose = root / "docker-compose.yml"
    if not compose.is_file():
        print("! No docker-compose.yml; skipping Postgres/Qdrant")
        return
    if _port_open("127.0.0.1", 5432) and _port_open("127.0.0.1", 6333):
        print("✓ Postgres and Qdrant already running")
        return
    docker = shutil.which("docker")
    if not docker:
        print("! docker not found; start Postgres (5432) and Qdrant (6333) yourself")
        return
    print("Starting Postgres and Qdrant…")
    # Stable project name so `apps/` vs the old RAGforge folder does not
    # recreate containers that already use container_name my_postgres_container.
    for project in ("dillema", "ragforge"):
        result = subprocess.run(
            [docker, "compose", "-p", project, "up", "-d"],
            cwd=root,
        )
        if result.returncode == 0:
            return
    if _port_open("127.0.0.1", 5432):
        print("! docker compose reported an error; Postgres is already on :5432, continuing")
        return
    print("! docker compose up failed; API may not reach the database")


def _ensure_npm_deps(web: Path) -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found. Install Node.js, then retry.")
    if not (web / "node_modules").is_dir():
        print("Installing frontend dependencies…")
        if subprocess.run([npm, "install"], cwd=web).returncode != 0:
            sys.exit("npm install failed")


def _app_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    venv = root / ".venv"
    if venv.is_dir():
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
        env.pop("UV_PROJECT", None)
        env.pop("UV_PROJECT_ENVIRONMENT", None)
    return env


def _uvicorn_cmd(root: Path, host: str, port: int) -> list[str]:
    # Use `python -m uvicorn` so stale console-script shebangs
    # (e.g. apps/RAGforge/.venv after the folder move) still work.
    venv_python = root / ".venv" / "bin" / "python"
    args = [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--reload",
        "--reload-dir",
        str(root / "app"),
        "--reload-dir",
        str(root / "rag"),
    ]
    if venv_python.is_file():
        return [str(venv_python), *args]
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--directory", str(root), "python", *args]
    sys.exit("apps/.venv is missing. Run `uv sync` in apps/.")


def _stop(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is not None:
            continue
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
    deadline = time.time() + 8
    for proc in procs:
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()


def start_dashboard(args) -> None:
    root = find_dashboard()
    web = root / "web"
    api_host = args.api_host
    api_port = args.api_port
    web_port = args.web_port

    if not args.no_docker:
        _ensure_docker(root)

    procs: list[subprocess.Popen] = []
    try:
        if _port_open("127.0.0.1", api_port):
            print(f"✓ API already running on :{api_port}")
        else:
            print(f"Starting DiLLeMa API on {api_host}:{api_port}…")
            procs.append(
                subprocess.Popen(
                    _uvicorn_cmd(root, api_host, api_port),
                    cwd=root,
                    env=_app_env(root),
                    start_new_session=True,
                )
            )

        if _port_open("127.0.0.1", web_port):
            print(f"✓ Web already running on :{web_port}")
        else:
            _ensure_npm_deps(web)
            npm = shutil.which("npm")
            env = os.environ.copy()
            env["VITE_BACKEND_URL"] = f"http://127.0.0.1:{api_port}"
            print(f"Starting DiLLeMa web on :{web_port}…")
            procs.append(
                subprocess.Popen(
                    [
                        npm,
                        "run",
                        "dev",
                        "--",
                        "--port",
                        str(web_port),
                        "--host",
                        "0.0.0.0",
                    ],
                    cwd=web,
                    env=env,
                    start_new_session=True,
                )
            )

        print(f"\n✓ API:       http://127.0.0.1:{api_port}")
        print(f"✓ Dashboard: http://127.0.0.1:{web_port}")
        print("Press Ctrl+C to stop\n")

        if not procs:
            return

        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"! A dashboard process exited (code {code})")
                    return
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping dashboard…")
    finally:
        _stop(procs)
