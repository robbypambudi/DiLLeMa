# dillema/__main__.py

import argparse
import logging
import sys

from dillema.common import print_banner
from dillema.ray_cluster.client_node import start_ray_worker
from dillema.ray_cluster.head_node import start_ray_head_node
from . import __version__


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print_banner()
    parser = argparse.ArgumentParser(description="Dillema: A package to manage Ray clusters and LLM deployments" ,
                                     usage="dillema <command> [<args>]")
    
    parser.error = lambda message: parser.print_help() or sys.exit(2)
    
    subparsers = parser.add_subparsers(dest="command", required=True)  # The 'required=True' ensures a command is provided

    # Subcommand for starting the Ray cluster
    start_parser = subparsers.add_parser("start", help="Start Ray cluster")
    start_parser.add_argument("node_type", choices=["head", "worker"], help="Type of node to start")
    start_parser.add_argument("--port", type=int, default=6379, help="Port for the Ray node")
    start_parser.add_argument("--address", type=str, default="localhost", help="Address of the head node (for worker)")

    
    args = parser.parse_args()


    if args.command == "start":
        if args.node_type == "head":
            start_ray_head_node(args)
        elif args.node_type == "worker":
            start_ray_worker(args)
        else:
            parser.print_help()
            sys.exit(2)

if __name__ == "__main__":
    main()
