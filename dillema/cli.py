import argparse
import subprocess
import socket
import ray
from ray import serve
from dillema.serve import LLMServe


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    finally:
        s.close()


def cmd_head(args):
    ip = get_local_ip()
    cmd = f"ray start --head --port={args.port} --dashboard-host={args.dashboard_host}"
    print(f"Starting Ray head node at {ip}:{args.port}")
    subprocess.run(cmd, shell=True)
    print(f"\n✓ Head node started!")
    print(f"✓ Connect workers with: dillema worker --address='{ip}:{args.port}'")
    print(f"✓ Dashboard: http://{ip}:8265")


def cmd_worker(args):
    cmd = f"ray start --address='{args.address}'"
    print(f"Connecting to head node at {args.address}")
    subprocess.run(cmd, shell=True)
    print(f"\n✓ Worker connected!")


def cmd_stop(args):
    print("Stopping Ray...")
    subprocess.run("ray stop", shell=True)
    print("✓ Ray stopped!")


def cmd_serve(args):
    ray.init(address=args.ray_address or "auto", ignore_reinit_error=True)
    
    wrapper = LLMServe(
        model_id=args.model_id,
        model_source=args.model_source,
        hf_token=args.hf_token,
        tensor_parallel_size=args.tensor_parallel,
        pipeline_parallel_size=args.pipeline_parallel,
    )
    
    app = wrapper.build_app(min_replicas=args.min_replicas, max_replicas=args.max_replicas)
    
    print(f"✓ Deploying {args.model_source}...")
    print(f"✓ Dashboard: http://localhost:8265")
    print(f"✓ API: http://localhost:8000")
    
    serve.run(app, blocking=True)


def main():
    parser = argparse.ArgumentParser(description="DiLLeMa - Distributed LLM")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Head
    head_parser = subparsers.add_parser("head", help="Start Ray head node")
    head_parser.add_argument("--port", type=int, default=6379, help="Ray port")
    head_parser.add_argument("--dashboard-host", default="0.0.0.0", help="Dashboard host")
    head_parser.set_defaults(func=cmd_head)
    
    # Worker
    worker_parser = subparsers.add_parser("worker", help="Start Ray worker node")
    worker_parser.add_argument("--address", required=True, help="Head node address (ip:port)")
    worker_parser.set_defaults(func=cmd_worker)
    
    # Stop
    stop_parser = subparsers.add_parser("stop", help="Stop Ray cluster")
    stop_parser.set_defaults(func=cmd_stop)
    
    # Serve
    serve_parser = subparsers.add_parser("serve", help="Deploy LLM model")
    serve_parser.add_argument("--model-id", required=True, help="Model identifier")
    serve_parser.add_argument("--model-source", required=True, help="HuggingFace model path")
    serve_parser.add_argument("--min-replicas", type=int, default=1, help="Minimum replicas")
    serve_parser.add_argument("--max-replicas", type=int, default=1, help="Maximum replicas")
    serve_parser.add_argument("--tensor-parallel", type=int, default=1, help="Tensor parallel size")
    serve_parser.add_argument("--pipeline-parallel", type=int, default=1, help="Pipeline parallel size")
    serve_parser.add_argument("--hf-token", help="HuggingFace token")
    serve_parser.add_argument("--ray-address", help="Ray cluster address")
    serve_parser.set_defaults(func=cmd_serve)
    
    args = parser.parse_args()
    
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
