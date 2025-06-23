#!/usr/bin/env python3
"""
Simple vLLM Multi-Node Launcher
Script sederhana untuk launch vLLM server di multi-node Ray cluster
"""

import subprocess
import os
import sys
import time
import signal

def fix_environment():
    """Fix CUDA environment"""
    if 'CUDA_VISIBLE_DEVICES' in os.environ:
        if os.environ['CUDA_VISIBLE_DEVICES'] == '':
            print("Removing empty CUDA_VISIBLE_DEVICES")
            del os.environ['CUDA_VISIBLE_DEVICES']
    
    os.environ['CUDA_LAUNCH_BLOCKING'] = '0'
    os.environ['NCCL_DEBUG'] = 'WARN'
    print("Environment fixed")

def run_single_gpu(model, port=8000):
    """Run vLLM dengan single GPU"""
    print(f"Starting vLLM server dengan single GPU...")
    print(f"Model: {model}")
    print(f"Port: {port}")
    
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model,
        "--tensor-parallel-size", "1",
        "--max-model-len", "2048",
        "--port", str(port),
        "--host", "0.0.0.0",
        "--trust-remote-code",
        "--enforce-eager",
        "--gpu-memory-utilization", "0.8",
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print("Starting server...")
    
    try:
        process = subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nShutting down...")

def run_multi_gpu(model, num_gpus=2, port=8000):
    """Run vLLM dengan multi-GPU tensor parallelism"""
    print(f"Starting vLLM server dengan {num_gpus} GPUs (tensor parallelism)...")
    print(f"Model: {model}")
    print(f"Port: {port}")
    
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model,
        "--tensor-parallel-size", str(num_gpus),
        "--pipeline-parallel-size", "1",
        "--max-model-len", "2048",
        "--port", str(port),
        "--host", "0.0.0.0",
        "--trust-remote-code",
        "--enforce-eager",
        "--gpu-memory-utilization", "0.8",
        "--distributed-executor-backend", "ray",
    ]
    
    print(f"Command: {' '.join(cmd)}")
    print("Starting server...")
    
    try:
        process = subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nShutting down...")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python simple_vllm_launcher.py single <model>")
        print("  python simple_vllm_launcher.py multi <model> [num_gpus]")
        print()
        print("Examples:")
        print("  python simple_vllm_launcher.py single Qwen/Qwen2.5-1.5B-Instruct")
        print("  python simple_vllm_launcher.py multi Qwen/Qwen2.5-1.5B-Instruct 2")
        return
    
    mode = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "Qwen/Qwen2.5-1.5B-Instruct"
    
    # Fix environment
    fix_environment()
    
    if mode == "single":
        run_single_gpu(model)
    elif mode == "multi":
        num_gpus = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        run_multi_gpu(model, num_gpus)
    else:
        print("Invalid mode. Use 'single' or 'multi'")

if __name__ == "__main__":
    main()