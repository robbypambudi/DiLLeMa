import time
import ray
import argparse
import logging

def start_ray_head_node(parse_arg: argparse.ArgumentParser):
    """
    Start a Ray head node on the given port.
    """
    logging.basicConfig(level=logging.INFO)

    try:
        ray.init(
            ignore_reinit_error=True,
            include_dashboard=True,
            object_store_memory=10**9,
            dashboard_host=parse_arg.dashboard_host,
            _node_name="head_node"
        )
        logging.info(f"Ray head node started on port {parse_arg.port}")
        
        # Create a dummy object to keep the program running
        while True:
            time.sleep(60)


    except Exception as e:
        logging.error(f"Failed to start Ray head node: {e}")
        raise


def main():
    """
    Main function to start a Ray head node.
    """
    parser = argparse.ArgumentParser(description="Start a Ray head node")

    parser.add_argument("--address", type=str, help="Address to start Ray head node on", default="localhost")
    parser.add_argument("--port", type=int, help="Port to start Ray head node on", default=6379)
    parser.add_argument("--dashboard_host", type=str, help="Dashboard Host", default="0.0.0.0")
    
    args = parser.parse_args()

    start_ray_head_node(args)

if __name__ == "__main__":
    main()