# dillema/__main__.py

import logging
import sys

from dillema.cli import cli_helper
from dillema.common import print_banner
from dillema.ray_cluster.client_node import start_ray_worker
from dillema.ray_cluster.head_node import start_ray_head_node


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print_banner()

    args = cli_helper().parse_args()

    if args.command == "start":
        if args.node_type == "head":
            start_ray_head_node(args)
        elif args.node_type == "worker":
            start_ray_worker(args)
        else:
            cli_helper().print_help()
            sys.exit(2)


if __name__ == "__main__":
    main()
