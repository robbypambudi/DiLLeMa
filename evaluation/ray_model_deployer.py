#!/usr/bin/env python3
"""
Ray Model Deployer
Script untuk deploy vLLM model ke Ray cluster
"""

import time
import logging
import json
import argparse

import ray
from ray import serve

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

@serve.deployment(
    name="vllm-model",
    num_replicas=1,
    ray_actor_options={"num_gpus": 1}
)
class VLLMModelDeployment:
    """vLLM Model Deployment untuk single GPU"""

    def __init__(self, model_name="Qwen/Qwen2.5-0.5B-Instruct", max_model_len=2048):
        logger.info(f"Loading model: {model_name}")

        # Import vLLM
        from vllm import LLM, SamplingParams

        # Initialize model dengan config untuk single GPU
        self.llm = LLM(
            model=model_name,
            tensor_parallel_size=1,  # Single GPU
            max_model_len=max_model_len,
            trust_remote_code=True,
            enforce_eager=True,
            gpu_memory_utilization=0.8,
            disable_log_stats=True,
        )

        self.model_name = model_name
        logger.info(f"Model {model_name} loaded successfully!")

    async def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7):
        """Generate text from prompt"""
        try:
            from vllm import SamplingParams

            sampling_params = SamplingParams(
                temperature=temperature,
                max_tokens=max_tokens,
                stop=["<|endoftext|>", "<|im_end|>"]
            )

            # Generate
            outputs = self.llm.generate([prompt], sampling_params)

            if outputs and len(outputs) > 0:
                output = outputs[0]
                generated_text = output.outputs[0].text

                # Estimate token counts
                prompt_tokens = len(prompt.split()) * 1.3
                completion_tokens = len(generated_text.split()) * 1.3

                return {
                    "text": generated_text,
                    "prompt_tokens": int(prompt_tokens),
                    "completion_tokens": int(completion_tokens),
                    "total_tokens": int(prompt_tokens + completion_tokens),
                    "model": self.model_name
                }

            return None

        except Exception as e:
            logger.error(f"Generation error: {e}")
            return {"error": str(e)}

    async def health_check(self):
        """Health check endpoint"""
        return {
            "status": "healthy",
            "model": self.model_name,
            "timestamp": time.time()
        }

    async def get_model_info(self):
        """Get model information"""
        return {
            "model_name": self.model_name,
            "tensor_parallel_size": 1,
            "max_model_len": 2048,
            "deployment_time": time.time()
        }

class ModelDeployer:
    """Class untuk manage deployment"""

    def __init__(self, ray_address=None):
        self.ray_address = ray_address
        self.connected = False

    def connect_to_cluster(self):
        """Connect ke Ray cluster"""
        logger.info(f"Connecting to Ray cluster: {self.ray_address or 'auto-detect'}")

        try:
            if self.ray_address:
                ray.init(address=self.ray_address, ignore_reinit_error=True)
            else:
                ray.init(address='auto', ignore_reinit_error=True)

            # Check cluster resources
            resources = ray.cluster_resources()
            logger.info(f"Cluster resources: {resources}")

            # Check GPU availability
            if 'GPU' not in resources or resources['GPU'] < 1:
                logger.error("No GPU available in cluster!")
                return False

            self.connected = True
            logger.info("Successfully connected to Ray cluster")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to cluster: {e}")
            return False

    def deploy_model(self, model_name="Qwen/Qwen2.5-0.5B-Instruct", max_model_len=2048):
        """Deploy model ke cluster"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        logger.info(f"Deploying model: {model_name}")

        try:
            # Create deployment
            deployment = VLLMModelDeployment.bind(model_name, max_model_len)

            # Deploy dengan route prefix
            serve.run(deployment, name="vllm-model", route_prefix="/")

            # Wait for deployment to be ready
            if self._wait_for_deployment():
                logger.info("Model deployed successfully!")
                self._save_deployment_info(model_name, max_model_len)
                return True
            else:
                logger.error("Deployment failed or timed out")
                return False

        except Exception as e:
            logger.error(f"Deployment error: {e}")
            return False

    def _wait_for_deployment(self, timeout=180):
        """Wait for deployment to be ready"""
        logger.info("Waiting for deployment to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Get status information as a ServeStatus object
                status_info = serve.status()
                logger.info(f"Deployment info: {status_info}")

                # Access the applications dictionary from the ServeStatus object
                if hasattr(status_info, "applications") and "vllm-model" in status_info.applications:
                    app_status = status_info.applications["vllm-model"].status.value
                    logger.info(f"Deployment status: {app_status}")
                    return app_status
                else:
                    logger.info("No deployment found")
                    return "NOT_DEPLOYED"
            except Exception as e:
                logger.debug(f"Still waiting for deployment: {e}")

            print(".", end="", flush=True)
            time.sleep(3)

        print()
        logger.error("Deployment timeout")
        return False

    def _save_deployment_info(self, model_name, max_model_len):
        """Save deployment info to file"""
        deployment_info = {
            "model_name": model_name,
            "max_model_len": max_model_len,
            "ray_address": self.ray_address,
            "deployment_time": time.time(),
            "status": "deployed"
        }

        with open("deployment_info.json", "w") as f:
            json.dump(deployment_info, f, indent=2)

        logger.info("Deployment info saved to deployment_info.json")

    def check_deployment_status(self):
        """Check current deployment status"""
        try:
            # Get status information as a ServeStatus object
            status_info = serve.status()
            logger.info(f"Deployment info: {status_info}")

            # Access the applications dictionary from the ServeStatus object
            if hasattr(status_info, "applications") and "vllm-model" in status_info.applications:
                app_status = status_info.applications["vllm-model"].status.value
                logger.info(f"Deployment status: {app_status}")
                return app_status
            else:
                logger.info("No deployment found")
                return "NOT_DEPLOYED"

        except Exception as e:
            logger.error(f"Error checking deployment status: {e}")
            return "ERROR"

    def stop_deployment(self):
        """Stop current deployment"""
        try:
            logger.info("Stopping deployment...")
            serve.shutdown()
            logger.info("Deployment stopped successfully")

            # Update deployment info
            try:
                with open("deployment_info.json", "r") as f:
                    info = json.load(f)
                info["status"] = "stopped"
                info["stop_time"] = time.time()

                with open("deployment_info.json", "w") as f:
                    json.dump(info, f, indent=2)
            except:
                pass

            return True
        except Exception as e:
            logger.error(f"Error stopping deployment: {e}")
            return False

    def get_cluster_info(self):
        """Get cluster information"""
        if not self.connected:
            return None

        try:
            return {
                "cluster_resources": ray.cluster_resources(),
                "available_resources": ray.available_resources(),
                "nodes": len(ray.nodes())
            }
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
            return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Deploy vLLM model to Ray cluster")
    parser.add_argument("--ray-address", type=str, default=None,
                        help="Ray cluster address (e.g., ray://localhost:10001)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct",
                        help="Model name to deploy")
    parser.add_argument("--max-len", type=int, default=2048,
                        help="Maximum model length")
    parser.add_argument("--action", type=str, choices=["deploy", "status", "stop"],
                        default="deploy", help="Action to perform")

    args = parser.parse_args()

    print("Ray Model Deployer")
    print("==================")

    deployer = ModelDeployer(args.ray_address)

    try:
        # Connect to cluster
        if not deployer.connect_to_cluster():
            print("Failed to connect to Ray cluster")
            return

        # Show cluster info
        cluster_info = deployer.get_cluster_info()
        if cluster_info:
            print(f"Cluster info:")
            print(f"  Total resources: {cluster_info['cluster_resources']}")
            print(f"  Available resources: {cluster_info['available_resources']}")
            print(f"  Nodes: {cluster_info['nodes']}")

        # Perform action
        if args.action == "deploy":
            print(f"\nDeploying model: {args.model}")
            if deployer.deploy_model(args.model, args.max_len):
                print("✓ Model deployed successfully!")
                print("You can now run the evaluator script.")
            else:
                print("✗ Deployment failed")

        elif args.action == "status":
            print(f"\nChecking deployment status...")
            status = deployer.check_deployment_status()
            print(f"Deployment status: {status}")

        elif args.action == "stop":
            print(f"\nStopping deployment...")
            if deployer.stop_deployment():
                print("✓ Deployment stopped successfully")
            else:
                print("✗ Failed to stop deployment")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect (don't shutdown cluster)
        try:
            ray.disconnect()
        except:
            pass

if __name__ == "__main__":
    main()