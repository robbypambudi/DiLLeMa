import json
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
        print(
            "! docker compose reported an error; Postgres is already on :5432, continuing"
        )
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


def _uv() -> str:
    uv = shutil.which("uv")
    if not uv:
        sys.exit("uv not found. Install uv, then run `uv sync` in apps/.")
    return uv


def _app_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Isolate from the root DiLLeMa uv project (ray/vllm).
    env.pop("UV_PROJECT", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT"] = str(root)
    env["UV_PROJECT_ENVIRONMENT"] = str(root / ".venv")
    return env


def _uv_run(root: Path, *args: str) -> list[str]:
    return [_uv(), "run", "--directory", str(root), *args]


def _ensure_project(root: Path) -> None:
    # Synced every start: a no-op when current, and it replaces a .venv left
    # behind by a failed sync or built on the wrong Python (apps/.python-version).
    print("Syncing dashboard environment with uv…")
    if subprocess.run([_uv(), "sync"], cwd=root, env=_app_env(root)).returncode != 0:
        sys.exit("uv sync failed in apps/. Fix the environment, then retry.")


def _ensure_migrations(root: Path) -> None:
    print("Applying database migrations…")
    result = subprocess.run(
        _uv_run(root, "python", "-m", "alembic", "upgrade", "head"),
        cwd=root,
        env=_app_env(root),
    )
    if result.returncode != 0:
        print("! alembic upgrade failed; API may error until you run:")
        print("  uv run --directory apps python -m alembic upgrade head")


def _uvicorn_cmd(root: Path, host: str, port: int) -> list[str]:
    return _uv_run(
        root,
        "python",
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


def _state_file() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return state / "dillema" / "dashboard.pids"


def _write_state(procs: list[subprocess.Popen]) -> None:
    """Record who to stop, so `dillema dashboard down` works from any shell."""
    path = _state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"launcher": os.getpid(), "children": [proc.pid for proc in procs]}
            )
        )
    except OSError as exc:
        print(f"! Could not record dashboard PIDs ({exc}); `down` will search for them")


def _read_state() -> dict | None:
    try:
        return json.loads(_state_file().read_text())
    except (OSError, ValueError):
        return None


def _clear_state(launcher: int | None = None) -> None:
    """Remove the record, but only our own when `launcher` is given."""
    state = _read_state()
    if launcher is not None and (state or {}).get("launcher") != launcher:
        return
    try:
        _state_file().unlink()
    except OSError:
        pass


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_gone(pids: list[int], seconds: float) -> list[int]:
    deadline = time.time() + seconds
    while time.time() < deadline:
        pids = [pid for pid in pids if _alive(pid)]
        if not pids:
            return []
        time.sleep(0.2)
    return [pid for pid in pids if _alive(pid)]


def _signal_group(pid: int, sig: int) -> None:
    """Children run in their own session, so pid is also their group id."""
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def _running_from(root: Path) -> list[int]:
    """API and web processes started from this checkout, for dashboards
    launched before PIDs were recorded. Linux only (/proc)."""
    web = root / "web"
    own_group = os.getpgid(0)
    found = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            cwd = Path(os.readlink(entry / "cwd"))
            cmdline = (
                (entry / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace")
            )
            pid = int(entry.name)
            if os.getpgid(pid) == own_group:
                continue
        except (OSError, ValueError):
            continue
        api = cwd == root and "uvicorn" in cmdline and "app.main:app" in cmdline
        ui = cwd == web and ("vite" in cmdline or "npm run dev" in cmdline)
        if api or ui:
            found.append(pid)
    return found


def stop_dashboard(args) -> None:
    root = find_dashboard()
    state = _read_state()
    targets: list[int] = []
    if state:
        launcher = state.get("launcher")
        if _alive(launcher):
            print(f"Stopping dashboard (launcher PID {launcher})…")
            # Its SIGTERM handler stops the API and web cleanly.
            os.kill(launcher, signal.SIGTERM)
            _wait_gone([launcher], 12)
        targets = [pid for pid in state.get("children", []) if _alive(pid)]
    else:
        targets = _running_from(root)

    if targets:
        print(f"Stopping dashboard processes {targets}…")
        for pid in targets:
            _signal_group(pid, signal.SIGTERM)
        for pid in _wait_gone(targets, 8):
            _signal_group(pid, signal.SIGKILL)
    _clear_state()

    if not state and not targets:
        print("✓ Dashboard is not running")
    else:
        print("✓ Dashboard stopped")

    if getattr(args, "docker", False):
        docker = shutil.which("docker")
        if not docker:
            print("! docker not found; Postgres/Qdrant left as they are")
            return
        print("Stopping Postgres and Qdrant (data is kept)…")
        for project in ("dillema", "ragforge"):
            subprocess.run([docker, "compose", "-p", project, "stop"], cwd=root)


def start_dashboard(args) -> None:
    root = find_dashboard()
    web = root / "web"
    api_host = args.api_host
    api_port = args.api_port
    web_port = args.web_port

    def terminate(signum, frame):
        raise KeyboardInterrupt

    procs: list[subprocess.Popen] = []
    previous_sigterm = signal.signal(signal.SIGTERM, terminate)
    try:
        if not args.no_docker:
            _ensure_docker(root)
        _ensure_project(root)
        _ensure_migrations(root)

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
            # The browser's API URL comes from BACKEND_URL in the repository
            # .env (vite.config.ts maps it); empty means same-origin `/api`.
            # The proxy behind `/api` runs on this machine, so loopback is right.
            env["DILLEMA_API_PROXY_TARGET"] = f"http://127.0.0.1:{api_port}"
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

        _write_state(procs)
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
        try:
            _stop(procs)
        finally:
            _clear_state(launcher=os.getpid())
            signal.signal(signal.SIGTERM, previous_sigterm)
