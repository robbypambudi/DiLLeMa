import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def find_ragforge() -> Path:
    env = os.environ.get("DILLEMA_RAGFORGE")
    if env:
        root = Path(env).expanduser().resolve()
        if (root / "app" / "main.py").is_file():
            return root
        sys.exit(f"DILLEMA_RAGFORGE={env} is not a DiLLeMa dashboard tree (missing app/main.py)")

    candidates = [
        Path(__file__).resolve().parents[1] / "apps" / "RAGforge",
        Path.cwd() / "apps" / "RAGforge",
    ]
    for root in candidates:
        if (root / "app" / "main.py").is_file():
            return root
    sys.exit(
        "DiLLeMa dashboard not found. Run this from the DiLLeMa repository "
        "or set DILLEMA_RAGFORGE to apps/RAGforge."
    )


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def _ensure_docker(ragforge: Path) -> None:
    compose = ragforge / "docker-compose.yml"
    if not compose.is_file():
        print("! No docker-compose.yml; skipping Postgres/Qdrant")
        return
    docker = shutil.which("docker")
    if not docker:
        print("! docker not found; start Postgres (5432) and Qdrant (6333) yourself")
        return
    print("Starting Postgres and Qdrant…")
    result = subprocess.run(
        [docker, "compose", "up", "-d"],
        cwd=ragforge,
    )
    if result.returncode != 0:
        print("! docker compose up failed; API may not reach the database")


def _ensure_npm_deps(web: Path) -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found. Install Node.js, then retry.")
    if not (web / "node_modules").is_dir():
        print("Installing frontend dependencies…")
        if subprocess.run([npm, "install"], cwd=web).returncode != 0:
            sys.exit("npm install failed")


def _uvicorn_cmd(ragforge: Path, host: str, port: int) -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [
            uv,
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ]
    venv_uvicorn = ragforge / ".venv" / "bin" / "uvicorn"
    if venv_uvicorn.is_file():
        return [str(venv_uvicorn), "app.main:app", "--host", host, "--port", str(port)]
    sys.exit(
        "uv not found and apps/RAGforge/.venv is missing. Run `uv sync` in apps/RAGforge."
    )


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
    ragforge = find_ragforge()
    web = ragforge / "web"
    api_host = args.api_host
    api_port = args.api_port
    web_port = args.web_port

    if not args.no_docker:
        _ensure_docker(ragforge)

    procs: list[subprocess.Popen] = []
    try:
        if _port_open("127.0.0.1", api_port):
            print(f"✓ API already running on :{api_port}")
        else:
            print(f"Starting DiLLeMa API on {api_host}:{api_port}…")
            procs.append(
                subprocess.Popen(
                    _uvicorn_cmd(ragforge, api_host, api_port),
                    cwd=ragforge,
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
