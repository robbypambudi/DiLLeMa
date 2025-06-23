#!/usr/bin/env python3
"""
Ray Model Deployer (Fixed)
Script untuk deploy vLLM model ke Ray cluster dengan proper GPU placement
"""

import time
import logging
import json
import argparse

import ray
from ray import serve
from ray.util.placement_group import placement_group
from ray.util.scheduling_strategies import PlacementGroupSchedulingStrategy

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

@serve.deployment(
    name="vllm-model",
    num_replicas=1,
    # Use placement_group_bundles instead of ray_actor_options for GPU placement
    placement_group_bundles=[
        {"CPU": 1, "GPU": 1},  # Main replica bundle with GPU
        {"CPU": 2}             # Additional CPU bundle for vLLM workers
    ],
    placement_group_strategy="STRICT_PACK"  # Keep all bundles on same node
)
class VLLMModelDeployment:
    """vLLM Model Deployment dengan proper GPU placement strategy"""

    def __init__(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048):
        logger.info(f"Loading model: {model_name}")

        # Import vLLM
        from vllm import LLM, SamplingParams

        # Initialize model dengan config untuk single GPU
        # Force vLLM to use Ray backend for proper GPU placement
        self.llm = LLM(
            model=model_name,
            tensor_parallel_size=1,  # Single GPU
            pipeline_parallel_size=1,  # Fix: changed from 2 to 1 for single GPU
            max_model_len=max_model_len,
            trust_remote_code=True,
            enforce_eager=True,
            gpu_memory_utilization=0.8,
            disable_log_stats=True,
            distributed_executor_backend="ray",  # Force Ray backend
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
    """Class untuk manage deployment dengan GPU placement strategy"""

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

            # Check if we have GPU nodes
            nodes = ray.nodes()
            gpu_nodes = [node for node in nodes if node.get('Resources', {}).get('GPU', 0) > 0]
            logger.info(f"Found {len(gpu_nodes)} GPU nodes in cluster")
            
            if len(gpu_nodes) == 0:
                logger.error("No GPU nodes found in cluster!")
                return False

            self.connected = True
            logger.info("Successfully connected to Ray cluster")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to cluster: {e}")
            return False

    def deploy_model(self, model_name="Qwen/Qwen2.5-0.5B-Instruct", max_model_len=2048):
        """Deploy model ke cluster dengan proper GPU placement"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        logger.info(f"Deploying model: {model_name}")

        try:
            # Create deployment dengan placement group untuk GPU
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
            import traceback
            traceback.print_exc()
            return False

    def deploy_model_with_custom_placement(self, model_name="Qwen/Qwen2.5-0.5B-Instruct", max_model_len=2048):
        """Alternative deployment method dengan manual placement group"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        logger.info(f"Deploying model with custom placement: {model_name}")

        try:
            # Create manual placement group for GPU resources
            # This ensures the deployment goes to a node with GPU
            pg = placement_group([
                {"CPU": 1, "GPU": 1},  # Main bundle with GPU
                {"CPU": 2}             # Additional CPU for workers
            ], strategy="STRICT_PACK")
            
            # Wait for placement group to be ready
            ray.get(pg.ready(), timeout=60)
            logger.info("Placement group created successfully")

            # Create deployment with custom decorator
            @serve.deployment(
                name="vllm-model",
                num_replicas=1,
                ray_actor_options={
                    "num_cpus": 1,
                    "num_gpus": 1,
                    "scheduling_strategy": PlacementGroupSchedulingStrategy(
                        placement_group=pg,
                        placement_group_bundle_index=0
                    )
                }
            )
            class CustomVLLMDeployment:
                def __init__(self):
                    logger.info(f"Loading model: {model_name}")
                    
                    from vllm import LLM, SamplingParams
                    
                    self.llm = LLM(
                        model=model_name,
                        tensor_parallel_size=1,
                        pipeline_parallel_size=1,
                        max_model_len=max_model_len,
                        trust_remote_code=True,
                        enforce_eager=True,
                        gpu_memory_utilization=0.8,
                        disable_log_stats=True,
                        distributed_executor_backend="ray",
                    )
                    
                    self.model_name = model_name
                    logger.info(f"Model {model_name} loaded successfully!")

                async def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7):
                    try:
                        from vllm import SamplingParams
                        
                        sampling_params = SamplingParams(
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stop=["<|endoftext|>", "<|im_end|>"]
                        )
                        
                        outputs = self.llm.generate([prompt], sampling_params)
                        
                        if outputs and len(outputs) > 0:
                            output = outputs[0]
                            generated_text = output.outputs[0].text
                            
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
                    return {
                        "status": "healthy",
                        "model": self.model_name,
                        "timestamp": time.time()
                    }

            # Deploy dengan custom placement
            deployment = CustomVLLMDeployment.bind()
            serve.run(deployment, name="vllm-model", route_prefix="/")

            # Wait for deployment to be ready
            if self._wait_for_deployment():
                logger.info("Model deployed successfully with custom placement!")
                self._save_deployment_info(model_name, max_model_len)
                return True
            else:
                logger.error("Deployment failed or timed out")
                return False

        except Exception as e:
            logger.error(f"Custom deployment error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _wait_for_deployment(self, timeout=300):  # Increased timeout for vLLM
        """Wait for deployment to be ready"""
        logger.info("Waiting for deployment to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                status_info = serve.status()
                logger.debug(f"Deployment info: {status_info}")

                if hasattr(status_info, "applications") and "vllm-model" in status_info.applications:
                    app_status = status_info.applications["vllm-model"].status.value
                    logger.info(f"Deployment status: {app_status}")
                    
                    if app_status == "RUNNING":
                        return True
                    elif app_status == "DEPLOY_FAILED":
                        logger.error("Deployment failed!")
                        return False
                else:
                    logger.debug("Deployment not found yet")

            except Exception as e:
                logger.debug(f"Still waiting for deployment: {e}")

            print(".", end="", flush=True)
            time.sleep(5)  # Increased sleep interval

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
            status_info = serve.status()
            logger.info(f"Deployment info: {status_info}")

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
            cluster_resources = ray.cluster_resources()
            available_resources = ray.available_resources()
            nodes = ray.nodes()
            
            gpu_nodes = [node for node in nodes if node.get('Resources', {}).get('GPU', 0) > 0]
            
            return {
                "cluster_resources": cluster_resources,
                "available_resources": available_resources,
                "total_nodes": len(nodes),
                "gpu_nodes": len(gpu_nodes),
                "gpu_node_details": [
                    {
                        "node_id": node.get("NodeID"),
                        "node_ip": node.get("NodeManagerAddress"),
                        "gpu_count": node.get('Resources', {}).get('GPU', 0),
                        "alive": node.get("Alive", False)
                    }
                    for node in gpu_nodes
                ]
            }
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
            return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Deploy vLLM model to Ray cluster")
    parser.add_argument("--ray-address", type=str, default=None,
                        help="Ray cluster address (e.g., ray://localhost:10001)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="Model name to deploy")
    parser.add_argument("--max-len", type=int, default=2048,
                        help="Maximum model length")
    parser.add_argument("--action", type=str, choices=["deploy", "deploy-custom", "status", "stop"],
                        default="deploy", help="Action to perform")

    args = parser.parse_args()

    print("Ray Model Deployer (Fixed)")
    print("===========================")

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
            print(f"  Total nodes: {cluster_info['total_nodes']}")
            print(f"  GPU nodes: {cluster_info['gpu_nodes']}")
            for gpu_node in cluster_info['gpu_node_details']:
                print(f"    Node {gpu_node['node_id'][:8]}...: {gpu_node['gpu_count']} GPUs, IP: {gpu_node['node_ip']}, Alive: {gpu_node['alive']}")

        # Perform action
        if args.action == "deploy":
            print(f"\nDeploying model: {args.model}")
            if deployer.deploy_model(args.model, args.max_len):
                print("✓ Model deployed successfully!")
                print("You can now run the evaluator script.")
            else:
                print("✗ Deployment failed")

        elif args.action == "deploy-custom":
            print(f"\nDeploying model with custom placement: {args.model}")
            if deployer.deploy_model_with_custom_placement(args.model, args.max_len):
                print("✓ Model deployed successfully with custom placement!")
                print("You can now run the evaluator script.")
            else:
                print("✗ Custom deployment failed")

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