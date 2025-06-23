#!/usr/bin/env python3
"""
vLLM Fixed Node Placement Deployer
Fix untuk masalah IP mapping dan node placement di multi-node Ray cluster
"""

import subprocess
import os
import sys
import time
import signal
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def check_gpu_availability():
    """Check GPU availability di current node"""
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            logger.info(f"✓ Found {gpu_count} GPU(s) on current node")
            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                logger.info(f"  GPU {i}: {gpu_name}")
            return gpu_count
        else:
            logger.error("✗ No CUDA GPUs available on current node")
            return 0
    except ImportError:
        logger.warning("PyTorch not available, cannot check GPU")
        return 0

def fix_environment():
    """Fix environment variables untuk vLLM"""
    # Remove empty CUDA_VISIBLE_DEVICES
    if 'CUDA_VISIBLE_DEVICES' in os.environ:
        if os.environ['CUDA_VISIBLE_DEVICES'] == '':
            logger.info("Removing empty CUDA_VISIBLE_DEVICES")
            del os.environ['CUDA_VISIBLE_DEVICES']
        else:
            logger.info(f"CUDA_VISIBLE_DEVICES: {os.environ['CUDA_VISIBLE_DEVICES']}")
    
    # Set helpful environment variables
    os.environ['CUDA_LAUNCH_BLOCKING'] = '0'
    os.environ['NCCL_DEBUG'] = 'WARN'
    os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
    
    # Important: Force vLLM to not use Ray for single GPU
    os.environ['VLLM_USE_RAY_COMPILED_DAG'] = 'False'
    
    logger.info("Environment variables fixed")

def run_single_gpu_safe(model, port=8000, max_len=2048):
    """Run vLLM dengan single GPU (paling aman)"""
    logger.info("Starting vLLM server dengan single GPU (safe mode)")
    logger.info(f"Model: {model}")
    logger.info(f"Port: {port}")
    
    # Check GPU first
    gpu_count = check_gpu_availability()
    if gpu_count == 0:
        logger.error("No GPU available on this node!")
        return False
    
    # Build command untuk single GPU
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model,
        "--tensor-parallel-size", "1",
        "--pipeline-parallel-size", "1",
        "--max-model-len", str(max_len),
        "--port", str(port),
        "--host", "0.0.0.0",
        "--trust-remote-code",
        "--enforce-eager",
        "--gpu-memory-utilization", "0.8",
        "--disable-log-stats",
        # Important: Force multiprocessing instead of Ray
        "--distributed-executor-backend", "mp",
    ]
    
    logger.info(f"Command: {' '.join(cmd)}")
    logger.info("Starting server...")
    
    try:
        process = subprocess.run(cmd)
        return True
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        return True
    except Exception as e:
        logger.error(f"Error running server: {e}")
        return False

def run_multi_gpu_ray_aware(model, num_gpus=2, port=8000, max_len=2048):
    """Run vLLM dengan multi-GPU dan explicit Ray node targeting"""
    logger.info(f"Starting vLLM server dengan {num_gpus} GPUs (Ray-aware)")
    
    # Import Ray untuk node information
    try:
        import ray
        
        # Connect to existing cluster
        ray.init(address='auto', ignore_reinit_error=True)
        
        # Get GPU nodes information
        nodes = ray.nodes()
        gpu_nodes = [node for node in nodes if node.get('Resources', {}).get('GPU', 0) > 0]
        
        logger.info(f"Found {len(gpu_nodes)} GPU nodes:")
        for i, node in enumerate(gpu_nodes):
            node_id = node.get("NodeID", "unknown")[:8]
            node_ip = node.get("NodeManagerAddress", "unknown")
            gpu_count = node.get('Resources', {}).get('GPU', 0)
            alive = node.get("Alive", False)
            logger.info(f"  Node {i+1}: {node_id}... - IP: {node_ip} - {gpu_count} GPU - Alive: {alive}")
        
        # Get current node info
        current_node_id = ray.get_runtime_context().get_node_id()
        logger.info(f"Current node ID: {current_node_id}")
        
        # Check if current node has GPU
        current_node = None
        for node in gpu_nodes:
            if node.get("NodeID") == current_node_id:
                current_node = node
                break
        
        if current_node is None:
            logger.warning("Current node is not a GPU node!")
            logger.info("Available GPU nodes:")
            for node in gpu_nodes:
                logger.info(f"  - {node.get('NodeManagerAddress')} (ID: {node.get('NodeID', '')[:8]}...)")
            
            # Fallback to single GPU
            logger.info("Falling back to single GPU mode...")
            ray.disconnect()
            return run_single_gpu_safe(model, port, max_len)
        
        logger.info(f"Current node has GPU: {current_node.get('Resources', {}).get('GPU', 0)}")
        ray.disconnect()
        
    except Exception as e:
        logger.error(f"Error checking Ray cluster: {e}")
        logger.info("Falling back to single GPU mode...")
        return run_single_gpu_safe(model, port, max_len)
    
    # Build command untuk multi-GPU dengan Ray
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model,
        "--tensor-parallel-size", str(num_gpus),
        "--pipeline-parallel-size", "1",
        "--max-model-len", str(max_len),
        "--port", str(port),
        "--host", "0.0.0.0",
        "--trust-remote-code",
        "--enforce-eager",
        "--gpu-memory-utilization", "0.8",
        "--disable-log-stats",
        "--distributed-executor-backend", "ray",
    ]
    
    logger.info(f"Command: {' '.join(cmd)}")
    logger.info("Starting multi-GPU server...")
    
    try:
        process = subprocess.run(cmd)
        return True
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        return True
    except Exception as e:
        logger.error(f"Error running multi-GPU server: {e}")
        logger.info("Trying fallback to single GPU...")
        return run_single_gpu_safe(model, port, max_len)

def run_on_specific_gpu_node(model, port=8000, max_len=2048):
    """Run vLLM pada node dengan GPU yang benar"""
    logger.info("Attempting to run on correct GPU node...")
    
    try:
        import ray
        ray.init(address='auto', ignore_reinit_error=True)
        
        # Get GPU nodes
        nodes = ray.nodes()
        gpu_nodes = [node for node in nodes if node.get('Resources', {}).get('GPU', 0) > 0 and node.get("Alive", False)]
        
        if not gpu_nodes:
            logger.error("No alive GPU nodes found!")
            return False
        
        # Use first available GPU node
        target_node = gpu_nodes[0]
        target_ip = target_node.get("NodeManagerAddress")
        target_id = target_node.get("NodeID", "")[:8]
        
        logger.info(f"Target GPU node: {target_id}... - IP: {target_ip}")
        
        # Submit vLLM job to specific node
        @ray.remote(num_gpus=1, num_cpus=2)
        def run_vllm_on_node():
            """Run vLLM server on this specific node"""
            import subprocess
            import os
            
            # Fix environment on target node
            if 'CUDA_VISIBLE_DEVICES' in os.environ:
                if os.environ['CUDA_VISIBLE_DEVICES'] == '':
                    del os.environ['CUDA_VISIBLE_DEVICES']
            
            os.environ['CUDA_LAUNCH_BLOCKING'] = '0'
            
            # Build command
            cmd = [
                "python", "-m", "vllm.entrypoints.openai.api_server",
                "--model", model,
                "--tensor-parallel-size", "1",
                "--pipeline-parallel-size", "1",
                "--max-model-len", str(max_len),
                "--port", str(port),
                "--host", "0.0.0.0",
                "--trust-remote-code",
                "--enforce-eager",
                "--gpu-memory-utilization", "0.8",
                "--disable-log-stats",
            ]
            
            return subprocess.run(cmd)
        
        # Submit job to GPU node
        logger.info("Submitting vLLM job to GPU node...")
        job = run_vllm_on_node.remote()
        
        # Wait for completion
        try:
            ray.get(job)
            return True
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            return True
            
    except Exception as e:
        logger.error(f"Error running on specific GPU node: {e}")
        return False
    finally:
        try:
            ray.disconnect()
        except:
            pass

def test_server(port=8000):
    """Test vLLM server"""
    try:
        import requests
        import time
        
        logger.info(f"Testing server on port {port}...")
        
        # Wait for server to be ready
        for i in range(30):
            try:
                response = requests.get(f"http://localhost:{port}/health", timeout=5)
                if response.status_code == 200:
                    break
            except:
                pass
            time.sleep(2)
            logger.info(f"Waiting for server... ({i+1}/30)")
        
        # Test completion
        url = f"http://localhost:{port}/v1/completions"
        data = {
            "model": "model",
            "prompt": "Hello, how are you?",
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        response = requests.post(url, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✓ Server test successful!")
            logger.info(f"Response: {result['choices'][0]['text']}")
            return True
        else:
            logger.error(f"Server test failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Server test error: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("vLLM Fixed Node Placement Deployer")
        print("==================================")
        print()
        print("Usage:")
        print("  python vllm_fixed_deployer.py single <model>     # Single GPU safe mode")
        print("  python vllm_fixed_deployer.py multi <model>      # Multi-GPU with Ray")
        print("  python vllm_fixed_deployer.py specific <model>   # Run on specific GPU node")
        print("  python vllm_fixed_deployer.py test               # Test server")
        print()
        print("Examples:")
        print("  python vllm_fixed_deployer.py single Qwen/Qwen2.5-1.5B-Instruct")
        print("  python vllm_fixed_deployer.py multi Qwen/Qwen2.5-1.5B-Instruct")
        print("  python vllm_fixed_deployer.py specific Qwen/Qwen2.5-1.5B-Instruct")
        print()
        print("Recommended untuk cluster Anda: single atau specific")
        return
    
    mode = sys.argv[1]
    
    if mode == "test":
        test_server()
        return
    
    model = sys.argv[2] if len(sys.argv) > 2 else "Qwen/Qwen2.5-1.5B-Instruct"
    
    # Fix environment
    fix_environment()
    
    if mode == "single":
        logger.info("=== SINGLE GPU SAFE MODE ===")
        run_single_gpu_safe(model)
    elif mode == "multi":
        logger.info("=== MULTI GPU RAY-AWARE MODE ===")
        run_multi_gpu_ray_aware(model)
    elif mode == "specific":
        logger.info("=== SPECIFIC GPU NODE MODE ===")
        run_on_specific_gpu_node(model)
    else:
        print("Invalid mode. Use 'single', 'multi', 'specific', or 'test'")

if __name__ == "__main__":
    main()