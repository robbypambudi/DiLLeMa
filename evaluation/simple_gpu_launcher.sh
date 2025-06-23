#!/bin/bash
# Simple GPU Node Launcher
# Script untuk run vLLM langsung di node dengan GPU

echo "Simple GPU Node Launcher untuk vLLM"
echo "==================================="

# Function to fix environment
fix_environment() {
    echo "Fixing environment variables..."
    
    # Remove empty CUDA_VISIBLE_DEVICES
    if [ "$CUDA_VISIBLE_DEVICES" = "" ]; then
        echo "Removing empty CUDA_VISIBLE_DEVICES"
        unset CUDA_VISIBLE_DEVICES
    fi
    
    # Set helpful environment variables
    export CUDA_LAUNCH_BLOCKING=0
    export NCCL_DEBUG=WARN
    export VLLM_WORKER_MULTIPROC_METHOD=spawn
    export VLLM_USE_RAY_COMPILED_DAG=False
    
    echo "Environment fixed"
}

# Function to check GPU
check_gpu() {
    echo "Checking GPU availability..."
    
    if command -v nvidia-smi &> /dev/null; then
        echo "nvidia-smi output:"
        nvidia-smi --list-gpus
        return 0
    else
        echo "nvidia-smi not found"
        return 1
    fi
}

# Function to run single GPU vLLM
run_single_gpu() {
    local model=${1:-"Qwen/Qwen2.5-1.5B-Instruct"}
    local port=${2:-8000}
    
    echo "Starting vLLM server with single GPU..."
    echo "Model: $model"
    echo "Port: $port"
    
    # Fix environment
    fix_environment
    
    # Check GPU
    if ! check_gpu; then
        echo "ERROR: No GPU detected on this node!"
        exit 1
    fi
    
    # Build and run command
    cmd="python -m vllm.entrypoints.openai.api_server \
        --model $model \
        --tensor-parallel-size 1 \
        --pipeline-parallel-size 1 \
        --max-model-len 2048 \
        --port $port \
        --host 0.0.0.0 \
        --trust-remote-code \
        --enforce-eager \
        --gpu-memory-utilization 0.8 \
        --disable-log-stats \
        --distributed-executor-backend mp"
    
    echo "Running command:"
    echo "$cmd"
    echo ""
    echo "Press Ctrl+C to stop server"
    echo ""
    
    # Run the command
    exec $cmd
}

# Function to show node info
show_node_info() {
    echo "Current Node Information:"
    echo "========================"
    echo "Hostname: $(hostname)"
    echo "IP addresses:"
    ip addr show | grep "inet " | grep -v "127.0.0.1"
    echo ""
    
    if command -v nvidia-smi &> /dev/null; then
        echo "GPU Information:"
        nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader,nounits
    else
        echo "No nvidia-smi found"
    fi
    echo ""
}

# Function to test server
test_server() {
    local port=${1:-8000}
    
    echo "Testing vLLM server on port $port..."
    
    # Wait for server to be ready
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
            echo "✓ Server is ready!"
            break
        fi
        echo "Waiting... ($i/30)"
        sleep 2
    done
    
    # Test completion
    echo "Testing completion endpoint..."
    curl -X POST "http://localhost:$port/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "model",
            "prompt": "Hello, how are you?",
            "max_tokens": 50,
            "temperature": 0.7
        }'
    echo ""
}

# Main script
case "${1:-help}" in
    "single")
        show_node_info
        run_single_gpu "$2" "$3"
        ;;
    "test")
        test_server "$2"
        ;;
    "info")
        show_node_info
        ;;
    "help"|*)
        echo "Usage:"
        echo "  $0 single [model] [port]     # Run single GPU vLLM server"
        echo "  $0 test [port]               # Test server"
        echo "  $0 info                      # Show node information"
        echo ""
        echo "Examples:"
        echo "  $0 single                                          # Use default model"
        echo "  $0 single Qwen/Qwen2.5-1.5B-Instruct            # Specify model"
        echo "  $0 single Qwen/Qwen2.5-1.5B-Instruct 8000       # Specify model and port"
        echo "  $0 test                                           # Test server on port 8000"
        echo "  $0 test 8000                                      # Test server on specific port"
        echo ""
        echo "Recommended untuk setup Anda:"
        echo "1. $0 info                    # Check node info first"
        echo "2. $0 single                  # Run vLLM server"
        echo "3. $0 test                    # Test server (dari terminal lain)"
        ;;
esac