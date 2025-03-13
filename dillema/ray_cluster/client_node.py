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

def main():
    # Argument parsing for head node IP and port to connect to
    parser = argparse.ArgumentParser(description="Connect worker node to Ray head node")
    parser.add_argument("--head-node-ip", type=str, help="IP address of the head node", required=True)
    parser.add_argument("--port", type=int, help="Port of the head node", default=6379)
    
    args = parser.parse_args()
    
    # Start the Ray worker node and connect to the head node
    start_ray_worker(args.head_node_ip, args.port)

if __name__ == "__main__":
    main()
