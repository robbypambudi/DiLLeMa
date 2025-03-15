import ray
import time
import logging

def start_ray_worker(data: dict):
    """
    Start Ray worker node and connect to an existing head node.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        # Ray initialization for worker node
        ray.init(
            ignore_reinit_error=True,  # Ignore error if Ray is already initialized
            address=f"{data.head_node_ip}:{data.port}",  # Connect to head node using IP and port
        )
        logging.info(f"Ray worker node connected to head node at {data.head_node_ip}:{data.port}")
        
        while True:
            time.sleep(60)

    except Exception as e:
        logging.error(f"Failed to start Ray worker node: {e}")
        raise