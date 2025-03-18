import time
import ray
import argparse
import logging


def start_ray_head_node(parse_arg: argparse.Namespace):
    """
    Start a Ray head node on the given port.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=True,
            object_store_memory=parse_arg.object_store_memory,
            dashboard_host=parse_arg.dashboard_host,
            _node_name="head_node",
        )
        while True:
            time.sleep(20)

    except Exception as e:
        logging.error(f"Failed to start Ray head node: {e}")
        raise

