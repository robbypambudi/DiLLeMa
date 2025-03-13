# dillema/__main__.py

import argparse
import logging
import sys

from dillema.common import print_banner
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


    if args.start:
        logging.info("Starting Ray cluster...")
        # Start Ray cluster
        pass
    else:
        logging.error("No valid command provided")
        parser.print_help()


if __name__ == "__main__":
    main()
