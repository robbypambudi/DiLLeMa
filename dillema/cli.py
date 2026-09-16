import argparse
import subprocess
import socket


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def cmd_head(args):
    ip = get_local_ip()
    cmd = [
        "ray",
        "start",
        "--head",
        f"--port={args.port}",
        f"--dashboard-host={args.dashboard_host}",
    ]
    print(f"Starting Ray head node at {ip}:{args.port}")
    if subprocess.run(cmd).returncode != 0:
        print("✗ Failed to start Ray head node.")
        return
    print(f"\n✓ Head node started!")
    print(f"✓ Connect workers with: dillema worker --address='{ip}:{args.port}'")
    print(f"✓ Dashboard: http://{ip}:8265")


def cmd_worker(args):
    cmd = ["ray", "start", f"--address={args.address}"]
    print(f"Connecting to head node at {args.address}")
    if subprocess.run(cmd).returncode != 0:
        print("✗ Failed to connect worker to head node.")
        return
    print(f"\n✓ Worker connected!")


def cmd_stop(args):
    print("Stopping Ray...")
    if subprocess.run(["ray", "stop"]).returncode != 0:
        print("✗ Failed to stop Ray.")
        return
    print("✓ Ray stopped!")


def cmd_serve(args):
    import ray
    from ray import serve
    from dillema.serve import LLMServe

    ray.init(address=args.ray_address or "auto", ignore_reinit_error=True)

    runtime_env = None
    if args.network_interface:
        runtime_env = {
            "env_vars": {
                "GLOO_SOCKET_IFNAME": args.network_interface,
                "NCCL_SOCKET_IFNAME": args.network_interface,
            }
        }

    wrapper = LLMServe(
        model_id=args.model_id,
        model_source=args.model_source,
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

    print(f"✓ Deploying {args.model_source}...")
    print(f"✓ Dashboard: http://{host}:8265")
    print(f"✓ API: http://{host}:{port}")

    serve.start(http_options=serve.config.HTTPOptions(host=host, port=port))
    serve.run(app, blocking=True)


def cmd_dashboard(args):
    from dillema.dashboard import start_dashboard

    start_dashboard(args)


def _add_dashboard_args(parser):
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
    parser = argparse.ArgumentParser(description="DiLLeMa - Distributed LLM")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Head
    head_parser = subparsers.add_parser("head", help="Start Ray head node")
    head_parser.add_argument("--port", type=int, default=6379, help="Ray port")
    head_parser.add_argument(
        "--dashboard-host", default="0.0.0.0", help="Dashboard host"
    )
    head_parser.set_defaults(func=cmd_head)

    # Worker
    worker_parser = subparsers.add_parser("worker", help="Start Ray worker node")
    worker_parser.add_argument(
        "--address", required=True, help="Head node address (ip:port)"
    )
    worker_parser.set_defaults(func=cmd_worker)

    # Stop
    stop_parser = subparsers.add_parser("stop", help="Stop Ray cluster")
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
        help="Start DiLLeMa API and web UI",
    )
    _add_dashboard_args(dashboard_parser)

    serve_parser = subparsers.add_parser("serve", help="Deploy LLM model")
    serve_parser.add_argument("--model-id", required=True, help="Model identifier")
    serve_parser.add_argument(
        "--model-source", required=True, help="HuggingFace model path"
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
        args.func(args)
    elif args.command == "start":
        start_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
