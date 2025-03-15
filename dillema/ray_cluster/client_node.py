import argparse
import ray
import time
import logging

def start_ray_worker(args: argparse.ArgumentParser):
    """
    Start Ray worker node and connect to an existing head node.
    """
    logging.basicConfig(level=logging.INFO)
    address = f"{args.head_host}:{args.head_port}"

    try:
        # Ray initialization for worker node
        ray.init(
            ignore_reinit_error=True,  # Ignore error if Ray is already initialized
            address=address
        )
        logging.info(f"Ray worker node connected to head node at {args.head_host}:{args.head_port}")
        
        while True:
            time.sleep(60)

    except Exception as e:
        logging.error(f"Failed to start Ray worker node: {e}")
        raise