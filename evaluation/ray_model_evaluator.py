#!/usr/bin/env python3
"""
Ray Model Evaluator
Script untuk evaluasi model yang sudah di-deploy di Ray cluster
"""

import time
import json
import psutil
import GPUtil
import numpy as np
import logging
import argparse
import asyncio
from typing import List, Dict

import ray
from ray import serve

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelEvaluator:
    """Evaluator untuk model yang sudah di-deploy"""

    def __init__(self, ray_address=None):
        self.ray_address = ray_address
        self.connected = False
        self.deployment_available = False

    def connect_to_cluster(self):
        """Connect ke Ray cluster"""
        logger.info(f"Connecting to Ray cluster: {self.ray_address or 'auto-detect'}")

        try:
            if self.ray_address:
                ray.init(address=self.ray_address, ignore_reinit_error=True)
            else:
                ray.init(address='auto', ignore_reinit_error=True)

            self.connected = True
            logger.info("Connected to Ray cluster")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to cluster: {e}")
            return False

    def check_deployment(self):
        """Check if model deployment is available"""
        if not self.connected:
            logger.error("Not connected to Ray cluster")
            return False

        try:
            # Get status information as a ServeStatus object
            status_info = serve.status()
            logger.info(f"Deployment info: {status_info}")

            # Access the applications dictionary from the ServeStatus object
            if hasattr(status_info, "applications") and "vllm-model" in status_info.applications:
                self.deployment_available = True
                app_status = status_info.applications["vllm-model"].status.value
                logger.info(f"Deployment status: {app_status}")
                return True
            else:
                logger.info("No deployment found")
                return False
        except Exception as e:
            logger.error(f"Error checking deployment: {e}")
            return False

    async def test_inference(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7):
        """Test single inference"""
        if not self.deployment_available:
            logger.error("No deployment available")
            return None

        logger.info(f"Testing inference: {prompt[:40]}...")

        # Collect system metrics before
        cpu_before = psutil.cpu_percent()
        ram_before = psutil.virtual_memory().percent

        try:
            gpus = GPUtil.getGPUs()
            gpu_before = gpus[0].load * 100 if gpus else 0
            gpu_mem_before = (gpus[0].memoryUsed / gpus[0].memoryTotal * 100) if gpus else 0
        except:
            gpu_before = 0
            gpu_mem_before = 0

        # Time the inference
        start_time = time.time()

        try:
            # Get deployment handle
            handle = serve.get_deployment_handle("vllm-model", "vllm-model")

            # Make inference request
            result = await handle.generate.remote(prompt, max_tokens, temperature)

            end_time = time.time()
            total_time = end_time - start_time

            # Collect system metrics after
            cpu_after = psutil.cpu_percent()
            ram_after = psutil.virtual_memory().percent

            try:
                gpus = GPUtil.getGPUs()
                gpu_after = gpus[0].load * 100 if gpus else 0
                gpu_mem_after = (gpus[0].memoryUsed / gpus[0].memoryTotal * 100) if gpus else 0
            except:
                gpu_after = 0
                gpu_mem_after = 0

            if result and "error" not in result:
                throughput = result['completion_tokens'] / total_time if total_time > 0 else 0

                evaluation_result = {
                    "prompt": prompt,
                    "response": result['text'],
                    "model": result.get('model', 'unknown'),
                    "total_time": total_time,
                    "prompt_tokens": result['prompt_tokens'],
                    "completion_tokens": result['completion_tokens'],
                    "total_tokens": result['total_tokens'],
                    "throughput": throughput,
                    "tokens_per_second": throughput,
                    "client_cpu_usage": (cpu_before + cpu_after) / 2,
                    "client_ram_usage": (ram_before + ram_after) / 2,
                    "client_gpu_usage": (gpu_before + gpu_after) / 2,
                    "client_gpu_memory": (gpu_mem_before + gpu_mem_after) / 2,
                    "timestamp": time.time()
                }

                logger.info(f"✓ Success: {total_time:.2f}s, {throughput:.1f} tokens/s")
                return evaluation_result
            else:
                logger.error(f"Inference failed: {result}")
                return None

        except Exception as e:
            logger.error(f"Inference error: {e}")
            return None

    async def run_single_prompt_evaluation(self, prompt: str, iterations: int = 3,
                                           max_tokens: int = 100, temperature: float = 0.7):
        """Run multiple iterations untuk single prompt"""
        logger.info(f"Evaluating prompt with {iterations} iterations: {prompt[:50]}...")

        results = []

        for i in range(iterations):
            result = await self.test_inference(prompt, max_tokens, temperature)
            if result:
                results.append(result)
                logger.info(f"  Iteration {i+1}: {result['total_time']:.2f}s, "
                            f"{result['throughput']:.1f} tok/s")

            # Small delay between iterations
            if i < iterations - 1:
                await asyncio.sleep(0.5)

        if results:
            # Calculate averages
            avg_result = {
                "prompt": prompt,
                "iterations": len(results),
                "avg_total_time": np.mean([r['total_time'] for r in results]),
                "avg_throughput": np.mean([r['throughput'] for r in results]),
                "avg_prompt_tokens": np.mean([r['prompt_tokens'] for r in results]),
                "avg_completion_tokens": np.mean([r['completion_tokens'] for r in results]),
                "avg_client_cpu": np.mean([r['client_cpu_usage'] for r in results]),
                "avg_client_ram": np.mean([r['client_ram_usage'] for r in results]),
                "avg_client_gpu": np.mean([r['client_gpu_usage'] for r in results]),
                "avg_client_gpu_mem": np.mean([r['client_gpu_memory'] for r in results]),
                "std_total_time": np.std([r['total_time'] for r in results]),
                "std_throughput": np.std([r['throughput'] for r in results]),
                "detailed_results": results,
                "model": results[0].get('model', 'unknown')
            }

            logger.info(f"Average results: {avg_result['avg_total_time']:.2f}s, "
                        f"{avg_result['avg_throughput']:.1f} tok/s")
            return avg_result

        return None

    async def run_batch_evaluation(self, prompts: List[str], iterations: int = 3,
                                   max_tokens: int = 100, temperature: float = 0.7):
        """Run evaluation untuk multiple prompts"""
        logger.info(f"Running batch evaluation: {len(prompts)} prompts x {iterations} iterations")

        all_results = []

        for i, prompt in enumerate(prompts):
            logger.info(f"\nPrompt {i+1}/{len(prompts)}")

            result = await self.run_single_prompt_evaluation(
                prompt, iterations, max_tokens, temperature
            )

            if result:
                all_results.append(result)

            # Delay between different prompts
            if i < len(prompts) - 1:
                await asyncio.sleep(1)

        return all_results

    def run_evaluation_sync(self, prompts: List[str] = None, iterations: int = 3,
                            max_tokens: int = 100, temperature: float = 0.7):
        """Synchronous wrapper untuk evaluation"""
        if prompts is None:
            prompts = [
                "What is artificial intelligence?",
                "Explain machine learning in simple terms.",
                "Write a short poem about technology.",
                "How do computers process information?",
                "What are the benefits of renewable energy?",
                "Describe the concept of neural networks.",
                "How does natural language processing work?",
                "What is the future of artificial intelligence?"
            ]

        async def _run_async():
            return await self.run_batch_evaluation(prompts, iterations, max_tokens, temperature)

        # Run async function
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(_run_async())
        except RuntimeError:
            return asyncio.run(_run_async())

    def print_summary(self, results: List[Dict]):
        """Print evaluation summary"""
        if not results:
            print("No results to summarize")
            return

        print("\n" + "="*70)
        print("MODEL EVALUATION SUMMARY")
        print("="*70)
        print(f"Ray cluster: {self.ray_address or 'auto-detected'}")
        print(f"Model: {results[0].get('model', 'unknown')}")
        print(f"Total prompts: {len(results)}")
        print(f"Iterations per prompt: {results[0].get('iterations', 'unknown')}")

        # Calculate overall statistics
        avg_time = np.mean([r['avg_total_time'] for r in results])
        avg_throughput = np.mean([r['avg_throughput'] for r in results])
        avg_prompt_tokens = np.mean([r['avg_prompt_tokens'] for r in results])
        avg_completion_tokens = np.mean([r['avg_completion_tokens'] for r in results])
        avg_cpu = np.mean([r['avg_client_cpu'] for r in results])
        avg_ram = np.mean([r['avg_client_ram'] for r in results])
        avg_gpu = np.mean([r['avg_client_gpu'] for r in results])
        avg_gpu_mem = np.mean([r['avg_client_gpu_mem'] for r in results])

        # Calculate variability
        std_time = np.std([r['avg_total_time'] for r in results])
        std_throughput = np.std([r['avg_throughput'] for r in results])

        print(f"\nPerformance Metrics:")
        print(f"  Average inference time: {avg_time:.2f}s (±{std_time:.2f}s)")
        print(f"  Average throughput: {avg_throughput:.2f} tokens/s (±{std_throughput:.2f})")
        print(f"  Average prompt tokens: {avg_prompt_tokens:.0f}")
        print(f"  Average completion tokens: {avg_completion_tokens:.0f}")

        print(f"\nClient Resource Usage:")
        print(f"  Average CPU usage: {avg_cpu:.1f}%")
        print(f"  Average RAM usage: {avg_ram:.1f}%")
        print(f"  Average GPU usage: {avg_gpu:.1f}%")
        print(f"  Average GPU memory: {avg_gpu_mem:.1f}%")

        print("="*70)

        # Per-prompt breakdown
        print("\nPer-prompt Results:")
        for i, result in enumerate(results):
            print(f"{i+1:2d}. {result['prompt'][:50]:50s} | "
                  f"Time: {result['avg_total_time']:5.2f}s | "
                  f"Throughput: {result['avg_throughput']:5.1f} tok/s")

    def save_results(self, results: List[Dict], filename: str = None):
        """Save evaluation results"""
        if filename is None:
            timestamp = int(time.time())
            filename = f"evaluation_results_{timestamp}.json"

        # Load deployment info if available
        deployment_info = {}
        try:
            with open("deployment_info.json", "r") as f:
                deployment_info = json.load(f)
        except:
            pass

        # Get cluster info
        cluster_info = {}
        try:
            if self.connected:
                cluster_info = {
                    "cluster_resources": ray.cluster_resources(),
                    "available_resources": ray.available_resources(),
                    "nodes": len(ray.nodes())
                }
        except:
            pass

        report = {
            "evaluation_timestamp": time.time(),
            "ray_cluster_address": self.ray_address or "auto-detected",
            "deployment_info": deployment_info,
            "cluster_info": cluster_info,
            "total_prompts": len(results),
            "results": results
        }

        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Results saved to {filename}")
        return filename

    def load_custom_prompts(self, filename: str):
        """Load custom prompts from file"""
        try:
            with open(filename, 'r') as f:
                if filename.endswith('.json'):
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    elif 'prompts' in data:
                        return data['prompts']
                else:
                    # Plain text file, one prompt per line
                    return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Failed to load prompts from {filename}: {e}")
            return None

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Evaluate vLLM model deployed on Ray cluster")
    parser.add_argument("--ray-address", type=str, default=None,
                        help="Ray cluster address")
    parser.add_argument("--prompts-file", type=str, default=None,
                        help="File containing custom prompts")
    parser.add_argument("--iterations", type=int, default=3,
                        help="Number of iterations per prompt")
    parser.add_argument("--max-tokens", type=int, default=100,
                        help="Maximum tokens to generate")
    parser.add_argument("--temperature", type=float, default=0.7,
                        help="Sampling temperature")
    parser.add_argument("--output", type=str, default=None,
                        help="Output filename for results")

    args = parser.parse_args()

    print("Ray Model Evaluator")
    print("===================")

    evaluator = ModelEvaluator(args.ray_address)

    try:
        # Connect to cluster
        if not evaluator.connect_to_cluster():
            print("Failed to connect to Ray cluster")
            return

        # Check deployment
        if not evaluator.check_deployment():
            print("No model deployment found. Please run the deployer first.")
            return

        # Load prompts
        prompts = None
        if args.prompts_file:
            prompts = evaluator.load_custom_prompts(args.prompts_file)
            if prompts:
                print(f"Loaded {len(prompts)} prompts from {args.prompts_file}")
            else:
                print("Failed to load custom prompts, using default prompts")

        # Quick test first
        print("\n=== Quick Test ===")
        quick_result = asyncio.run(evaluator.test_inference("Hello! How are you today?"))
        if quick_result:
            print(f"✓ Quick test successful: {quick_result['total_time']:.2f}s, "
                  f"{quick_result['throughput']:.1f} tokens/s")
        else:
            print("✗ Quick test failed")
            return

        # Full evaluation
        print("\n=== Full Evaluation ===")
        results = evaluator.run_evaluation_sync(
            prompts=prompts,
            iterations=args.iterations,
            max_tokens=args.max_tokens,
            temperature=args.temperature
        )

        if results:
            # Print summary
            evaluator.print_summary(results)

            # Save results
            output_file = evaluator.save_results(results, args.output)
            print(f"\n✓ Evaluation completed! Results saved to {output_file}")
        else:
            print("No results obtained")

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Disconnect from cluster
        try:
            ray.disconnect()
        except:
            pass

if __name__ == "__main__":
    main()