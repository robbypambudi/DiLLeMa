#!/usr/bin/env python3
"""
Ray Model Deployer untuk Multi-Node Setup
Script untuk deploy vLLM model ke Ray cluster dengan 2 server terpisah (masing-masing 1 GPU)
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
    # Konfigurasi untuk multi-node dengan 2 GPU (1 per server)
    placement_group_bundles=[
        {"CPU": 2, "GPU": 1},  # Bundle untuk server 1
        {"CPU": 2, "GPU": 1},  # Bundle untuk server 2
    ],
    placement_group_strategy="SPREAD"  # Spread across different nodes
)
class VLLMModelDeploymentMultiNode:
    """vLLM Model Deployment untuk multi-node cluster (2 server, masing-masing 1 GPU)"""

    def __init__(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048, use_tensor_parallel=True):
        logger.info(f"Loading model: {model_name} on multi-node cluster")
        
        # Import vLLM
        from vllm import LLM, SamplingParams

        if use_tensor_parallel:
            # Tensor parallelism: split model across 2 GPUs
            logger.info("Using tensor parallelism across 2 GPUs")
            self.llm = LLM(
                model=model_name,
                tensor_parallel_size=2,  # 2 GPUs across nodes
                pipeline_parallel_size=1,
                max_model_len=max_model_len,
                trust_remote_code=True,
                enforce_eager=True,
                gpu_memory_utilization=0.8,
                disable_log_stats=True,
                distributed_executor_backend="ray",  # Force Ray backend
            )
        else:
            # Pipeline parallelism: different layers on different GPUs
            logger.info("Using pipeline parallelism across 2 GPUs")
            self.llm = LLM(
                model=model_name,
                tensor_parallel_size=1,
                pipeline_parallel_size=2,  # 2 stages across nodes
                max_model_len=max_model_len,
                trust_remote_code=True,
                enforce_eager=True,
                gpu_memory_utilization=0.8,
                disable_log_stats=True,
                distributed_executor_backend="ray",
            )

        self.model_name = model_name
        self.use_tensor_parallel = use_tensor_parallel
        logger.info(f"Model {model_name} loaded successfully on multi-node cluster!")

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
                    "model": self.model_name,
                    "parallelism": "tensor" if self.use_tensor_parallel else "pipeline"
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
            "parallelism": "tensor" if self.use_tensor_parallel else "pipeline",
            "timestamp": time.time()
        }

    async def get_model_info(self):
        """Get model information"""
        return {
            "model_name": self.model_name,
            "tensor_parallel_size": 2 if self.use_tensor_parallel else 1,
            "pipeline_parallel_size": 1 if self.use_tensor_parallel else 2,
            "max_model_len": 2048,
            "deployment_time": time.time(),
            "parallelism_type": "tensor" if self.use_tensor_parallel else "pipeline"
        }

# Deployment khusus untuk single node (fallback)
@serve.deployment(
    name="vllm-model-single",
    num_replicas=1,
    ray_actor_options={"num_gpus": 1, "num_cpus": 2}
)
class VLLMModelDeploymentSingle:
    """vLLM Model Deployment untuk single GPU (jika hanya 1 server available)"""

    def __init__(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048):
        logger.info(f"Loading model: {model_name} on single GPU")

        from vllm import LLM, SamplingParams

        self.llm = LLM(
            model=model_name,
            tensor_parallel_size=1,  # Single GPU
            pipeline_parallel_size=1,
            max_model_len=max_model_len,
            trust_remote_code=True,
            enforce_eager=True,
            gpu_memory_utilization=0.8,
            disable_log_stats=True,
        )

        self.model_name = model_name
        logger.info(f"Model {model_name} loaded successfully on single GPU!")

    async def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7):
        """Generate text from prompt"""
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
                    "model": self.model_name,
                    "parallelism": "single"
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
            "parallelism": "single",
            "timestamp": time.time()
        }

class ModelDeployer:
    """Class untuk manage deployment multi-node"""

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

            # Analyze node configuration
            nodes = ray.nodes()
            gpu_nodes = [node for node in nodes if node.get('Resources', {}).get('GPU', 0) > 0]
            
            logger.info(f"Found {len(gpu_nodes)} GPU nodes in cluster")
            logger.info(f"Total GPUs available: {resources['GPU']}")
            
            if len(gpu_nodes) == 0:
                logger.error("No GPU nodes found in cluster!")
                return False

            # Display node details
            for i, node in enumerate(gpu_nodes):
                node_id = node.get("NodeID", "unknown")[:8]
                node_ip = node.get("NodeManagerAddress", "unknown")
                gpu_count = node.get('Resources', {}).get('GPU', 0)
                cpu_count = node.get('Resources', {}).get('CPU', 0)
                alive = node.get("Alive", False)
                
                logger.info(f"  GPU Node {i+1}: {node_id}... - IP: {node_ip} - {gpu_count} GPU, {cpu_count} CPU - Alive: {alive}")

            self.connected = True
            logger.info("Successfully connected to Ray cluster")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to cluster: {e}")
            return False

    def deploy_model_multi_node(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048, use_tensor_parallel=True):
        """Deploy model untuk multi-node cluster (2 GPU across 2 servers)"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        # Check if we have at least 2 GPUs
        resources = ray.cluster_resources()
        if resources.get('GPU', 0) < 2:
            logger.warning("Less than 2 GPUs available, falling back to single GPU deployment")
            return self.deploy_model_single_node(model_name, max_model_len)

        logger.info(f"Deploying model for multi-node: {model_name}")
        parallelism_type = "tensor parallelism" if use_tensor_parallel else "pipeline parallelism"
        logger.info(f"Using {parallelism_type} across 2 GPU nodes")

        try:
            # Create deployment
            deployment = VLLMModelDeploymentMultiNode.bind(model_name, max_model_len, use_tensor_parallel)

            # Deploy dengan route prefix
            serve.run(deployment, name="vllm-model", route_prefix="/")

            # Wait for deployment to be ready
            if self._wait_for_deployment():
                logger.info("Multi-node model deployed successfully!")
                self._save_deployment_info(model_name, max_model_len, "multi_node", parallelism_type)
                return True
            else:
                logger.error("Multi-node deployment failed or timed out")
                return False

        except Exception as e:
            logger.error(f"Multi-node deployment error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def deploy_model_single_node(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048):
        """Deploy model untuk single GPU (fallback)"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        logger.info(f"Deploying model for single GPU: {model_name}")

        try:
            # Create deployment
            deployment = VLLMModelDeploymentSingle.bind(model_name, max_model_len)

            # Deploy dengan route prefix
            serve.run(deployment, name="vllm-model", route_prefix="/")

            # Wait for deployment to be ready
            if self._wait_for_deployment():
                logger.info("Single GPU model deployed successfully!")
                self._save_deployment_info(model_name, max_model_len, "single_node", "single_gpu")
                return True
            else:
                logger.error("Single GPU deployment failed or timed out")
                return False

        except Exception as e:
            logger.error(f"Single GPU deployment error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def deploy_model_custom_placement(self, model_name="Qwen/Qwen2.5-1.5B-Instruct", max_model_len=2048):
        """Deploy dengan manual placement group untuk kontrol penuh"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        logger.info(f"Deploying model with custom placement: {model_name}")

        try:
            # Create placement group yang spread across nodes
            pg = placement_group([
                {"CPU": 2, "GPU": 1},  # Bundle 1: Server 1
                {"CPU": 2, "GPU": 1},  # Bundle 2: Server 2
            ], strategy="SPREAD")  # Force different nodes
            
            # Wait for placement group to be ready
            ray.get(pg.ready(), timeout=120)
            logger.info("Multi-node placement group created successfully")

            # Create deployment dengan custom scheduling
            @serve.deployment(
                name="vllm-model",
                num_replicas=1,
                ray_actor_options={
                    "num_cpus": 2,
                    "num_gpus": 2,  # Total 2 GPUs
                    "scheduling_strategy": PlacementGroupSchedulingStrategy(
                        placement_group=pg,
                        placement_group_capture_child_tasks=True
                    )
                }
            )
            class CustomMultiNodeVLLM:
                def __init__(self):
                    logger.info(f"Loading model with custom placement: {model_name}")
                    
                    from vllm import LLM, SamplingParams
                    
                    # Use tensor parallelism across 2 nodes
                    self.llm = LLM(
                        model=model_name,
                        tensor_parallel_size=2,  # 2 GPUs across nodes
                        pipeline_parallel_size=1,
                        max_model_len=max_model_len,
                        trust_remote_code=True,
                        enforce_eager=True,
                        gpu_memory_utilization=0.8,
                        disable_log_stats=True,
                        distributed_executor_backend="ray",
                    )
                    
                    self.model_name = model_name
                    logger.info(f"Model {model_name} loaded with custom placement!")

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
                                "model": self.model_name,
                                "placement": "custom_multi_node"
                            }
                        
                        return None
                        
                    except Exception as e:
                        logger.error(f"Generation error: {e}")
                        return {"error": str(e)}

                async def health_check(self):
                    return {
                        "status": "healthy",
                        "model": self.model_name,
                        "placement": "custom_multi_node",
                        "timestamp": time.time()
                    }

            # Deploy dengan custom placement
            deployment = CustomMultiNodeVLLM.bind()
            serve.run(deployment, name="vllm-model", route_prefix="/")

            # Wait for deployment to be ready
            if self._wait_for_deployment():
                logger.info("Model deployed successfully with custom multi-node placement!")
                self._save_deployment_info(model_name, max_model_len, "custom_multi_node", "tensor_parallel")
                return True
            else:
                logger.error("Custom deployment failed or timed out")
                return False

        except Exception as e:
            logger.error(f"Custom deployment error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _wait_for_deployment(self, timeout=300):
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
            time.sleep(5)

        print()
        logger.error("Deployment timeout")
        return False

    def _save_deployment_info(self, model_name, max_model_len, deployment_type, parallelism):
        """Save deployment info to file"""
        deployment_info = {
            "model_name": model_name,
            "max_model_len": max_model_len,
            "deployment_type": deployment_type,
            "parallelism": parallelism,
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
        """Get detailed cluster information"""
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
                "total_gpus": cluster_resources.get('GPU', 0),
                "available_gpus": available_resources.get('GPU', 0),
                "gpu_node_details": [
                    {
                        "node_id": node.get("NodeID", "unknown")[:8],
                        "node_ip": node.get("NodeManagerAddress", "unknown"),
                        "gpu_count": node.get('Resources', {}).get('GPU', 0),
                        "cpu_count": node.get('Resources', {}).get('CPU', 0),
                        "alive": node.get("Alive", False)
                    }
                    for node in gpu_nodes
                ],
                "deployment_recommendation": self._get_deployment_recommendation(gpu_nodes, cluster_resources)
            }
        except Exception as e:
            logger.error(f"Error getting cluster info: {e}")
            return None

    def _get_deployment_recommendation(self, gpu_nodes, cluster_resources):
        """Get deployment recommendation based on cluster config"""
        total_gpus = cluster_resources.get('GPU', 0)
        num_gpu_nodes = len(gpu_nodes)
        
        if total_gpus >= 2 and num_gpu_nodes >= 2:
            return "multi_node_tensor_parallel"
        elif total_gpus >= 2 and num_gpu_nodes == 1:
            return "single_node_multi_gpu"
        elif total_gpus == 1:
            return "single_node_single_gpu"
        else:
            return "no_gpu_available"

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Deploy vLLM model to multi-node Ray cluster")
    parser.add_argument("--ray-address", type=str, default=None,
                        help="Ray cluster address (e.g., ray://localhost:10001)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-1.5B-Instruct",
                        help="Model name to deploy")
    parser.add_argument("--max-len", type=int, default=2048,
                        help="Maximum model length")
    parser.add_argument("--action", type=str, 
                        choices=["deploy-multi", "deploy-single", "deploy-custom", "status", "stop"],
                        default="deploy-multi", help="Action to perform")
    parser.add_argument("--parallelism", type=str, choices=["tensor", "pipeline"],
                        default="tensor", help="Parallelism strategy for multi-node")

    args = parser.parse_args()

    print("Ray Model Deployer untuk Multi-Node")
    print("===================================")
    print("Setup: 2 Server fisik terpisah, masing-masing 1 GPU")
    print()

    deployer = ModelDeployer(args.ray_address)

    try:
        # Connect to cluster
        if not deployer.connect_to_cluster():
            print("Failed to connect to Ray cluster")
            return

        # Show cluster info
        cluster_info = deployer.get_cluster_info()
        if cluster_info:
            print(f"Cluster Configuration:")
            print(f"  Total resources: {cluster_info['cluster_resources']}")
            print(f"  Available resources: {cluster_info['available_resources']}")
            print(f"  Total nodes: {cluster_info['total_nodes']}")
            print(f"  GPU nodes: {cluster_info['gpu_nodes']}")
            print(f"  Total GPUs: {cluster_info['total_gpus']}")
            print(f"  Available GPUs: {cluster_info['available_gpus']}")
            print(f"  Recommended deployment: {cluster_info['deployment_recommendation']}")
            print()
            
            print("GPU Node Details:")
            for i, gpu_node in enumerate(cluster_info['gpu_node_details']):
                print(f"  Server {i+1}: {gpu_node['node_id']}... - IP: {gpu_node['node_ip']}")
                print(f"    GPUs: {gpu_node['gpu_count']}, CPUs: {gpu_node['cpu_count']}, Status: {'Online' if gpu_node['alive'] else 'Offline'}")

        print()

        # Perform action
        if args.action == "deploy-multi":
            print(f"Deploying model untuk multi-node: {args.model}")
            print(f"Parallelism strategy: {args.parallelism}")
            use_tensor = args.parallelism == "tensor"
            if deployer.deploy_model_multi_node(args.model, args.max_len, use_tensor):
                print("✓ Multi-node model deployed successfully!")
                print("Model tersebar di 2 server GPU Anda")
                print("You can now run the evaluator script.")
            else:
                print("✗ Multi-node deployment failed")

        elif args.action == "deploy-single":
            print(f"Deploying model untuk single GPU: {args.model}")
            if deployer.deploy_model_single_node(args.model, args.max_len):
                print("✓ Single GPU model deployed successfully!")
                print("You can now run the evaluator script.")
            else:
                print("✗ Single GPU deployment failed")

        elif args.action == "deploy-custom":
            print(f"Deploying model dengan custom placement: {args.model}")
            if deployer.deploy_model_custom_placement(args.model, args.max_len):
                print("✓ Custom multi-node model deployed successfully!")
                print("Model tersebar di 2 server dengan custom placement")
                print("You can now run the evaluator script.")
            else:
                print("✗ Custom deployment failed")

        elif args.action == "status":
            print(f"Checking deployment status...")
            status = deployer.check_deployment_status()
            print(f"Deployment status: {status}")

        elif args.action == "stop":
            print(f"Stopping deployment...")
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