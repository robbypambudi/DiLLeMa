import argparse
import os
import ray
import time
import logging

def start_ray_worker(args: argparse.ArgumentParser):
    """
    Start Ray worker node and connect to an existing head node.
    """
    logging.basicConfig(level=logging.INFO)
    address = f"{args.head_host}:{args.head_port}"

    # Temp dir must absolute path or None.
    temp_dir = os.path.abspath("temp")

    try:
        # Ray initialization for worker node
        ray.init(
            ignore_reinit_error=True,  # Ignore error if Ray is already initialized
            address=address,
            _temp_dir=temp_dir
        )
        logging.info(f"Ray worker node connected to head node at {args.head_host}:{args.head_port}")
        
        while True:
            time.sleep(60)

    except Exception as e:
        logging.error(f"Failed to start Ray worker node: {e}")
        raise