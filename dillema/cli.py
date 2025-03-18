import argparse
import sys
import ray


def serve_model(args):
    """
    Serve model via FastAPI server
    """
    ray.init(address="auto")
    print("Menjalankan server FastAPI...")


def cli_helper() -> argparse.ArgumentParser:
    top_level_parser = argparse.ArgumentParser(
        prog="dillema",
        description="Dillema: A package to manage Ray clusters and LLM deployments",
    )
    top_level_parser.error = lambda message: top_level_parser.print_help() \
        or sys.exit(2)

    command_subparser = top_level_parser.add_subparsers(dest="command", required=True)

    # serve parser
    serve_parser = command_subparser.add_parser("serve")
    serve_parser.add_argument(
        "--model", type=str, required=True, help="Nama model atau path model"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="Port untuk API server"
    )

    # node head/worker parser
    node_parser = command_subparser.add_parser("start", help="Start Ray cluster")

    node_type_subparser = node_parser.add_subparsers(dest="node_type", required=True)

    head_parser = node_type_subparser.add_parser("head")
    head_parser.add_argument(
        "--dashboard-host",
        type=str,
        default="0.0.0.0",
        help="Host for the Ray dashboard",
    )
    head_parser.add_argument(
        "--object-store-memory",
        type=int,
        default=10**9,
        help="Memory for the Ray object store",
    )

    worker_parser = node_type_subparser.add_parser("worker")
    worker_parser.add_argument(
        "--head-host",
        type=str,
        default="localhost",
        help="IP address of the head node (for worker)",
        required=True,
    )
    worker_parser.add_argument(
        "--head-port", type=int, default=6379, help="Port of the head node (for worker)"
    )

    return top_level_parser

