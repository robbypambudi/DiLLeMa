import ray
import argparse
import logging

def start_ray_worker(head_node_ip: str, port: int):
    """
    Start Ray worker node and connect to an existing head node.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Ray initialization for worker node
        ray.init(
            ignore_reinit_error=True,  # Ignore error if Ray is already initialized
            address=f"{head_node_ip}:{port}",  # Connect to head node using IP and port
        )
        logging.info(f"Ray worker node connected to head node at {head_node_ip}:{port}")
        
        # Here you can add the code to do worker tasks, for now, the worker will just run indefinitely.
        while True:
            # Simulating worker activity (you can add real worker tasks here)
            logging.info("Worker node is running...")
            ray.sleep(60)  # Sleep to keep the worker node alive

    except Exception as e:
        logging.error(f"Failed to start Ray worker node: {e}")
        raise