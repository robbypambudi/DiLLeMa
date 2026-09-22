import argparse
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from dillema.env import load_dillema_env, model_id_from_env, model_source_from_env


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def _ray_temp_dir_args() -> list[str]:
    # RAY_TMPDIR moves Ray's temp dir (sessions, logs, spilled objects) off
    # /tmp, which may be a RAM-backed tmpfs. `ray.init`, `ray status` and
    # `ray stop` read the env var; `ray start` needs the flag too, because a
    # worker started without it reuses the head's temp dir path.
    root = os.environ.get("RAY_TMPDIR", "").strip()
    if not root:
        return []
    return [f"--temp-dir={os.path.join(root, 'ray')}"]


def cmd_head(args):
    ip = args.node_ip_address or get_local_ip()
    cmd = [
        "ray",
        "start",
        "--head",
        f"--port={args.port}",
        f"--dashboard-host={args.dashboard_host}",
    ]
    if args.node_ip_address:
        # On a multi-homed host (e.g. a VPN), Ray otherwise advertises the
        # default-route IP, which other nodes may not be able to reach.
        cmd.append(f"--node-ip-address={args.node_ip_address}")
    cmd += _ray_temp_dir_args()
    if args.num_cpus is not None:
        # 0 keeps the head a coordinator only: on a head without a GPU, the
        # ingress and other CPU actors then run on the GPU worker, next to
        # the model, instead of here.
        cmd.append(f"--num-cpus={args.num_cpus}")
    print(f"Starting Ray head node at {ip}:{args.port}")
    if subprocess.run(cmd).returncode != 0:
        print("✗ Failed to start Ray head node.")
        return
    print(f"\n✓ Head node started!")
    print(f"✓ Connect workers with: dillema worker --address='{ip}:{args.port}'")
    print(f"✓ Ray dashboard: http://{ip}:8265")


def cmd_worker(args):
    cmd = ["ray", "start", f"--address={args.address}"]
    if args.node_ip_address:
        cmd.append(f"--node-ip-address={args.node_ip_address}")
    cmd += _ray_temp_dir_args()
    print(f"Connecting to head node at {args.address}")
    if subprocess.run(cmd).returncode != 0:
        print("✗ Failed to connect worker to head node.")
        return
    print(f"\n✓ Worker connected!")


def cmd_stop(args):
    cmd = ["ray", "stop"]
    if args.force:
        cmd.append("--force")
    print("Stopping Ray...")
    if subprocess.run(cmd).returncode != 0:
        print("✗ Failed to stop Ray.")
        return
    print("✓ Ray stopped!")


def _ray_cluster_up() -> bool:
    ray_bin = shutil.which("ray")
    if not ray_bin:
        return False
    result = subprocess.run(
        [ray_bin, "status"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_ray(address: str | None) -> str:
    if address and address != "auto":
        return address
    if _ray_cluster_up():
        print("✓ Ray cluster already running")
        return "auto"
    ray_bin = shutil.which("ray")
    if not ray_bin:
        sys.exit("ray CLI not found. Install the DiLLeMa environment with `uv sync`.")
    ip = get_local_ip()
    print(f"No Ray cluster found; starting head at {ip}:6379…")
    cmd = [
        ray_bin,
        "start",
        "--head",
        "--port=6379",
        "--dashboard-host=0.0.0.0",
        *_ray_temp_dir_args(),
    ]
    if subprocess.run(cmd).returncode != 0:
        sys.exit("Failed to start Ray head node.")
    print(f"✓ Ray head started (dashboard http://{ip}:8265)")
    return "auto"


def cmd_serve(args):
    # Under `uv run`, Ray would otherwise make every worker `uv run` (and sync
    # dependencies) again. Workers instead use the Python that `ray start`
    # runs on their own node. Read at import time, so it is set before `ray`.
    os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")
    import ray
    from ray import serve
    from dillema.serve import LLMServe

    model_id = args.model_id or model_id_from_env()
    model_source = args.model_source or model_source_from_env()
    if not model_id or not model_source:
        sys.exit(
            "Model is not configured. Set LLM_MODEL and LLM_MODEL_SOURCE in .env "
            "(or pass --model-id and --model-source)."
        )

    ray_address = _ensure_ray(args.ray_address)
    ray.init(address=ray_address, ignore_reinit_error=True)

    runtime_env = None
    if args.network_interface:
        runtime_env = {
            "env_vars": {
                "GLOO_SOCKET_IFNAME": args.network_interface,
                "NCCL_SOCKET_IFNAME": args.network_interface,
            }
        }

    wrapper = LLMServe(
        model_id=model_id,
        model_source=model_source,
        hf_token=args.hf_token,
        tensor_parallel_size=args.tensor_parallel,
        pipeline_parallel_size=args.pipeline_parallel,
    )

    app = wrapper.build_app(
        min_replicas=args.min_replicas,
        max_replicas=args.max_replicas,
        runtime_env=runtime_env,
    )

    host = args.app_host or "0.0.0.0"
    port = args.app_port or 8000

    print(f"✓ Deploying {model_id} from {model_source}…")
    print(f"✓ Ray dashboard: http://{host}:8265")
    print(f"✓ OpenAI API: http://{host}:{port}/v1")

    serve.start(http_options=serve.config.HTTPOptions(host=host, port=port))
    serve.run(app, blocking=True)


def cmd_dashboard(args):
    from dillema.dashboard import start_dashboard, stop_dashboard

    if getattr(args, "action", "up") == "down":
        stop_dashboard(args)
    else:
        start_dashboard(args)


def _start_detached(args):
    command = [sys.executable, "-u", "-m", "dillema.cli", args.command]
    if args.command == "start":
        command.append(args.target)
    for name, value in vars(args).items():
        if name in {"command", "target", "func", "detach", "action"} or value is None:
            continue
        flag = "--" + name.replace("_", "-")
        if isinstance(value, bool):
            if value:
                command.append(flag)
        else:
            command.append(f"{flag}={value}")

    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    log_dir = state / "dillema"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="ab",
            prefix=f"{args.command}-",
            suffix=".log",
            dir=log_dir,
            delete=False,
        ) as log:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as exc:
        sys.exit(f"Failed to start background process: {exc}")
    print(
        f"✓ Background process launched (PID {proc.pid}); startup continues in the log."
    )
    print(f"✓ Logs: tail -f {shlex.quote(log.name)}")
    print(f"✓ Stop process: kill {proc.pid}")
    if args.command == "serve":
        print("✓ Stop the Ray cluster and model: dillema stop")


def _add_detach_arg(parser):
    parser.add_argument(
        "-d",
        "--detach",
        action="store_true",
        help="Run in the background and write output to a log file",
    )


def _add_dashboard_args(parser):
    _add_detach_arg(parser)
    parser.add_argument("--api-host", default="0.0.0.0", help="Dashboard API host")
    parser.add_argument("--api-port", type=int, default=8080, help="Dashboard API port")
    parser.add_argument("--web-port", type=int, default=3000, help="Dashboard web port")
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Do not run docker compose for Postgres/Qdrant",
    )
    parser.set_defaults(func=cmd_dashboard)


def main():
    load_dillema_env()

    parser = argparse.ArgumentParser(description="DiLLeMa - Distributed LLM")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Head
    head_parser = subparsers.add_parser("head", help="Start Ray head node")
    head_parser.add_argument("--port", type=int, default=6379, help="Ray port")
    head_parser.add_argument(
        "--dashboard-host", default="0.0.0.0", help="Ray dashboard host"
    )
    head_parser.add_argument(
        "--num-cpus",
        type=int,
        default=None,
        help="CPUs the head offers to workloads; 0 schedules nothing on it "
        "(use on a head without a GPU)",
    )
    head_parser.add_argument(
        "--node-ip-address",
        default=None,
        help="IP this node advertises to the cluster (e.g. its VPN IP)",
    )
    head_parser.set_defaults(func=cmd_head)

    # Worker
    worker_parser = subparsers.add_parser("worker", help="Start Ray worker node")
    worker_parser.add_argument(
        "--address", required=True, help="Head node address (ip:port)"
    )
    worker_parser.add_argument(
        "--node-ip-address",
        default=None,
        help="IP this node advertises to the cluster (e.g. its VPN IP)",
    )
    worker_parser.set_defaults(func=cmd_worker)

    # Stop
    stop_parser = subparsers.add_parser("stop", help="Stop Ray cluster")
    stop_parser.add_argument(
        "--force",
        action="store_true",
        help="Kill Ray processes with SIGKILL (clears stale raylets)",
    )
    stop_parser.set_defaults(func=cmd_stop)

    start_parser = subparsers.add_parser("start", help="Start apps")
    start_sub = start_parser.add_subparsers(dest="target")
    dashboard_start = start_sub.add_parser(
        "dashboard",
        help="Start DiLLeMa API and web UI",
    )
    _add_dashboard_args(dashboard_start)

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Start (up, default) or stop (down) the DiLLeMa API and web UI",
    )
    dashboard_parser.add_argument(
        "action",
        nargs="?",
        choices=["up", "down"],
        default="up",
        help="up starts the dashboard; down stops a running one",
    )
    dashboard_parser.add_argument(
        "--docker",
        action="store_true",
        help="With down: also stop the Postgres and Qdrant containers (data is kept)",
    )
    _add_dashboard_args(dashboard_parser)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start Ray if needed and deploy the LLM from env or flags",
    )
    _add_detach_arg(serve_parser)
    serve_parser.add_argument(
        "--model-id",
        default=None,
        help="Model identifier (default: LLM_MODEL from .env)",
    )
    serve_parser.add_argument(
        "--model-source",
        default=None,
        help="HuggingFace model path (default: LLM_MODEL_SOURCE or TEXT_GENERATION_MODEL)",
    )
    serve_parser.add_argument(
        "--min-replicas", type=int, default=1, help="Minimum replicas"
    )
    serve_parser.add_argument(
        "--max-replicas", type=int, default=1, help="Maximum replicas"
    )
    serve_parser.add_argument(
        "--tensor-parallel", type=int, default=1, help="Tensor parallel size"
    )
    serve_parser.add_argument(
        "--pipeline-parallel", type=int, default=1, help="Pipeline parallel size"
    )
    serve_parser.add_argument("--hf-token", help="HuggingFace token")
    serve_parser.add_argument("--ray-address", help="Ray cluster address")
    serve_parser.add_argument(
        "--network-interface",
        help="Network interface for distributed communication (e.g., eth0, enp132s0)",
    )
    serve_parser.add_argument("--app-host", help="Application host address")
    serve_parser.add_argument(
        "--app-port", type=int, default=8000, help="Application port number"
    )
    serve_parser.set_defaults(func=cmd_serve)

    args = parser.parse_args()

    if hasattr(args, "func"):
        # Stopping is immediate; only starting is worth detaching.
        if getattr(args, "detach", False) and getattr(args, "action", "up") != "down":
            _start_detached(args)
        else:
            args.func(args)
    elif args.command == "start":
        start_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
