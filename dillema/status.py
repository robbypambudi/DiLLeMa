"""What is running right now, in one screen.

A DiLLeMa deployment is several processes on possibly several machines: a Ray
head and its workers, a model served behind Ray Serve, Qdrant and Postgres,
and the dashboard's API and web app. Finding out which of them are up
otherwise means half a dozen curl calls and remembering every port.

Every check is a read: an HTTP GET or a TCP connect, nothing is started,
stopped or written. Checks run together and each gives up quickly, so the
command answers in about the time of its slowest probe rather than the sum.
"""

import json
import os
import socket
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_TIMEOUT = 2.0
# Wide enough for "2 nodes, 1 GPU" or a model name, narrow enough that the
# address column still lands in the same place on every row.
DETAIL_WIDTH = 34

OK, DOWN, UNKNOWN = "ok", "down", "unknown"
_MARKS = {OK: "●", DOWN: "○", UNKNOWN: "·"}
_COLOURS = {OK: "\033[32m", DOWN: "\033[31m", UNKNOWN: "\033[90m"}
_RESET = "\033[0m"
_DIM = "\033[90m"


def _colour(enabled: bool):
    if enabled:
        return lambda text, code: f"{code}{text}{_RESET}"
    return lambda text, _code: text


def _get_json(url: str, timeout: float):
    """Parsed JSON from a GET, or None when anything at all goes wrong."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _reachable(url: str, timeout: float) -> bool:
    """Whether the URL answers at all; any HTTP status counts as answering.

    A 404 still proves something is listening and speaking HTTP, which is what
    this column claims -- not that the path exists.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _host_of(url: str, fallback: str = "localhost") -> str:
    return urlsplit(url).hostname or fallback


def _state_file() -> Path:
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return state / "dillema" / "dashboard.pids"


def _alive(pid) -> bool:
    """Whether that process exists. Only a positive PID is a process.

    `os.kill(-1, 0)` means "every process I may signal" and succeeds, so a
    corrupted state file would otherwise report a dead dashboard as running.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def check_ray(host: str, timeout: float) -> tuple[str, str, str]:
    """Nodes and GPUs the cluster currently has, from the dashboard API."""
    address = f"http://{host}:8265"
    payload = _get_json(f"{address}/nodes?view=summary", timeout)
    if payload is None:
        return DOWN, "not reachable", address
    nodes = (payload.get("data") or {}).get("summary") or []
    alive = [n for n in nodes if (n.get("raylet") or {}).get("state") == "ALIVE"]
    gpus = sum(len(n.get("gpus") or []) for n in alive)
    detail = f"{len(alive)} node" + ("s" if len(alive) != 1 else "")
    if gpus:
        detail += f", {gpus} GPU" + ("s" if gpus != 1 else "")
    return OK, detail, address


def check_serve(host: str, timeout: float) -> tuple[str, str, str]:
    """Ray Serve applications, which is where a dead replica becomes visible."""
    address = f"http://{host}:8265"
    payload = _get_json(f"{address}/api/serve/applications/", timeout)
    if payload is None:
        return UNKNOWN, "no Serve controller", address
    apps = payload.get("applications") or {}
    if not apps:
        return UNKNOWN, "nothing deployed", address
    unhealthy = [
        f"{name}: {app.get('status')}"
        for name, app in apps.items()
        if app.get("status") != "RUNNING"
    ]
    if unhealthy:
        return DOWN, "; ".join(unhealthy), address
    deployments = sum(len(app.get("deployments") or {}) for app in apps.values())
    return OK, f"{len(apps)} app, {deployments} deployments", address


def check_llm(base_url: str, timeout: float) -> tuple[str, str, str]:
    """The served model, named. An endpoint that lists no model is not ready."""
    payload = _get_json(f"{base_url.rstrip('/')}/models", timeout)
    if payload is None:
        return DOWN, "not reachable", base_url
    models = [row.get("id") for row in (payload.get("data") or []) if row.get("id")]
    if not models:
        return DOWN, "no model loaded", base_url
    return OK, ", ".join(models[:2]), base_url


def check_qdrant(host: str, port: int, timeout: float) -> tuple[str, str, str]:
    address = f"http://{host}:{port}"
    payload = _get_json(f"{address}/collections", timeout)
    if payload is None:
        return DOWN, "not reachable", address
    names = [
        row.get("name")
        for row in ((payload.get("result") or {}).get("collections") or [])
    ]
    if not names:
        return OK, "no collections yet", address
    listed = ", ".join(n for n in names[:2] if n)
    more = f" +{len(names) - 2}" if len(names) > 2 else ""
    return OK, f"{len(names)}: {listed}{more}", address


def check_postgres(host: str, port: int, database: str, timeout: float):
    """A TCP connect only: proving the database answers needs a driver and a
    password, and this command is not the place to use either."""
    address = f"{host}:{port}"
    if _port_open(host, port, timeout):
        return OK, f"port open ({database})" if database else "port open", address
    return DOWN, "not reachable", address


def check_http(label_url: str, timeout: float) -> tuple[str, str, str]:
    if _reachable(label_url, timeout):
        return OK, "responding", label_url
    return DOWN, "not reachable", label_url


def check_local_processes() -> tuple[str, str, str]:
    """The dashboard this machine started, from the PID file `dashboard up` writes."""
    path = _state_file()
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return UNKNOWN, "none recorded here", str(path)
    children = [pid for pid in (state.get("children") or []) if _alive(pid)]
    dead = len(state.get("children") or []) - len(children)
    if not children:
        return DOWN, "recorded but not running", str(path)
    detail = f"{len(children)} process" + ("es" if len(children) != 1 else "")
    if dead:
        detail += f", {dead} exited"
    return OK, detail, str(path)


def gather(timeout: float) -> list[tuple[str, str, str, str]]:
    """Run every probe at once; each row is (label, state, detail, address)."""
    llm_base = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
    ray_host = _host_of(os.environ.get("RAY_DASHBOARD_URL", ""), _host_of(llm_base))
    api_url = os.environ.get("BACKEND_URL") or "http://localhost:8080"
    web_url = f"http://{_host_of(api_url)}:{os.environ.get('WEB_PORT', '3000')}"
    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", "6333") or 6333)
    pg_host = os.environ.get("POSTGRES_SERVER", "localhost")
    pg_port = int(os.environ.get("POSTGRES_PORT", "5432") or 5432)
    pg_db = os.environ.get("POSTGRES_DB", "")

    jobs = [
        ("Ray cluster", lambda: check_ray(ray_host, timeout)),
        ("Ray Serve", lambda: check_serve(ray_host, timeout)),
        ("LLM endpoint", lambda: check_llm(llm_base, timeout)),
        ("Qdrant", lambda: check_qdrant(qdrant_host, qdrant_port, timeout)),
        ("Postgres", lambda: check_postgres(pg_host, pg_port, pg_db, timeout)),
        ("Dashboard API", lambda: check_http(f"{api_url.rstrip('/')}/docs", timeout)),
        ("Dashboard web", lambda: check_http(web_url, timeout)),
        ("Local processes", check_local_processes),
    ]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        results = list(pool.map(lambda job: job[1](), jobs))
    return [(label, *result) for (label, _), result in zip(jobs, results)]


def print_status(timeout: float = DEFAULT_TIMEOUT, colour: bool | None = None) -> int:
    from dillema import __version__

    paint = _colour(os.isatty(1) if colour is None else colour)
    rows = gather(timeout)
    width = max(len(row[0]) for row in rows)
    detail_width = min(DETAIL_WIDTH, max(len(row[2]) for row in rows))
    print(f"\nDiLLeMa {__version__}\n")
    for label, state, detail, address in rows:
        mark = paint(_MARKS[state], _COLOURS[state])
        if len(detail) > detail_width:
            detail = detail[: detail_width - 1] + "…"
        print(
            f"  {mark} {label:<{width}}  {detail:<{detail_width}}  {paint(address, _DIM)}"
        )
    down = [row[0] for row in rows if row[1] == DOWN]
    print()
    if down:
        print(f"  {len(down)} not reachable: {', '.join(down)}\n")
    return 0
