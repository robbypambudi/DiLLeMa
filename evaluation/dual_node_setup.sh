#!/bin/bash
# Dual Node Setup Script
# Script untuk setup vLLM di 2 node dengan IP dan port forwarding berbeda

echo "Dual Node vLLM Setup"
echo "===================="

# Node configuration
NODE1_EXTERNAL_IP="216.234.102.170"
NODE1_PORTS="10804-10820"
NODE1_SSH_PORT="10803"

NODE2_EXTERNAL_IP="70.62.164.140"
NODE2_PORTS="20101-20123"
NODE2_SSH_PORT="20100"

# Default settings
DEFAULT_INTERNAL_PORT="8000"
DEFAULT_MODEL="Qwen/Qwen2.5-1.5B-Instruct"

# Function to show configuration
show_config() {
    echo "Node Configuration:"
    echo "=================="
    echo "Node 1:"
    echo "  External IP: $NODE1_EXTERNAL_IP"
    echo "  SSH Port: $NODE1_SSH_PORT"
    echo "  Available Ports: $NODE1_PORTS"
    echo ""
    echo "Node 2:"
    echo "  External IP: $NODE2_EXTERNAL_IP" 
    echo "  SSH Port: $NODE2_SSH_PORT"
    echo "  Available Ports: $NODE2_PORTS"
    echo ""
}

# Function to detect current node
detect_node() {
    echo "Detecting current node..."
    
    # Check hostname
    HOSTNAME=$(hostname)
    echo "Hostname: $HOSTNAME"
    
    # Check internal IP
    INTERNAL_IP=$(ip route get 8.8.8.8 | awk '{print $7}' | head -n1)
    echo "Internal IP: $INTERNAL_IP"
    
    # Ask user for confirmation since auto-detection might not be perfect
    echo ""
    echo "Which node are you currently on?"
    echo "1) Node 1 ($NODE1_EXTERNAL_IP)"
    echo "2) Node 2 ($NODE2_EXTERNAL_IP)"
    read -p "Select (1 or 2): " node_choice
    
    case $node_choice in
        1)
            CURRENT_NODE="node1"
            EXTERNAL_IP="$NODE1_EXTERNAL_IP"
            PORT_RANGE="$NODE1_PORTS"
            echo "Selected: Node 1"
            ;;
        2)
            CURRENT_NODE="node2"
            EXTERNAL_IP="$NODE2_EXTERNAL_IP"
            PORT_RANGE="$NODE2_PORTS"
            echo "Selected: Node 2"
            ;;
        *)
            echo "Invalid selection. Defaulting to Node 1"
            CURRENT_NODE="node1"
            EXTERNAL_IP="$NODE1_EXTERNAL_IP"
            PORT_RANGE="$NODE1_PORTS"
            ;;
    esac
    
    echo "Current node: $CURRENT_NODE"
    echo "External IP: $EXTERNAL_IP"
    echo "Port range: $PORT_RANGE"
}

# Function to select port
select_port() {
    local default_port=$1
    
    echo ""
    echo "Select vLLM port:"
    
    if [ "$CURRENT_NODE" = "node1" ]; then
        echo "Available ports for Node 1: 10804, 10805, 10806, 10807, 10808, 10809..."
        echo "Recommended: 10808 (for vLLM API)"
        read -p "Enter port [$default_port]: " selected_port
        selected_port=${selected_port:-$default_port}
        
        # Validate port is in range 10804-10820
        if [ "$selected_port" -ge 10804 ] && [ "$selected_port" -le 10820 ]; then
            VLLM_PORT=$selected_port
        else
            echo "Port $selected_port not in forwarded range. Using default: $default_port"
            VLLM_PORT=$default_port
        fi
    else
        echo "Available ports for Node 2: 20101, 20109, 20111, 20112, 20113..."
        echo "Recommended: 20115 (for vLLM API)"
        read -p "Enter port [$default_port]: " selected_port
        selected_port=${selected_port:-$default_port}
        
        # Validate port is in range 20101-20123
        if [ "$selected_port" -ge 20101 ] && [ "$selected_port" -le 20123 ]; then
            VLLM_PORT=$selected_port
        else
            echo "Port $selected_port not in forwarded range. Using default: $default_port"
            VLLM_PORT=$default_port
        fi
    fi
    
    echo "Selected port: $VLLM_PORT"
}

# Function to setup environment
setup_environment() {
    echo ""
    echo "Setting up environment..."
    
    # Remove empty CUDA_VISIBLE_DEVICES
    if [ "$CUDA_VISIBLE_DEVICES" = "" ]; then
        echo "Removing empty CUDA_VISIBLE_DEVICES"
        unset CUDA_VISIBLE_DEVICES
    fi
    
    # Set multi-node environment variables
    export CUDA_LAUNCH_BLOCKING=0
    export NCCL_DEBUG=INFO
    export NCCL_SOCKET_IFNAME=eth0
    export VLLM_HOST_IP=$INTERNAL_IP
    export VLLM_WORKER_MULTIPROC_METHOD=spawn
    export NCCL_IB_DISABLE=1
    export NCCL_P2P_DISABLE=1
    export RAY_DISABLE_IMPORT_WARNING=1
    
    echo "Environment variables set:"
    echo "  VLLM_HOST_IP: $VLLM_HOST_IP"
    echo "  NCCL_SOCKET_IFNAME: $NCCL_SOCKET_IFNAME"
    echo "  Current node: $CURRENT_NODE"
}

# Function to check Ray cluster
check_ray_cluster() {
    echo ""
    echo "Checking Ray cluster..."
    
    if command -v ray &> /dev/null; then
        echo "Ray cluster status:"
        ray status 2>/dev/null || echo "Warning: Could not get Ray status"
        
        echo ""
        echo "Ray nodes:"
        ray list nodes 2>/dev/null || echo "Warning: Could not list Ray nodes"
    else
        echo "Ray command not found"
    fi
}

# Function to run vLLM
run_vllm() {
    local model=$1
    local use_multi_node=${2:-"auto"}
    
    echo ""
    echo "Starting vLLM Server"
    echo "==================="
    echo "Model: $model"
    echo "Current Node: $CURRENT_NODE"
    echo "Internal IP: $INTERNAL_IP"
    echo "vLLM Port: $VLLM_PORT"
    echo "External Access: http://$EXTERNAL_IP:$VLLM_PORT"
    echo ""
    
    # Determine tensor parallel size
    if [ "$use_multi_node" = "multi" ]; then
        TENSOR_PARALLEL_SIZE=2
        DISTRIBUTED_BACKEND="ray"
        echo "Mode: Multi-node (2 GPUs across 2 nodes)"
    elif [ "$use_multi_node" = "single" ]; then
        TENSOR_PARALLEL_SIZE=1
        DISTRIBUTED_BACKEND="mp"
        echo "Mode: Single GPU"
    else
        # Auto-detect based on Ray cluster
        GPU_COUNT=$(ray status 2>/dev/null | grep "Total Usage" -A 5 | grep "GPU" | awk '{print $1}' | cut -d'/' -f2 || echo "1")
        if [ "$GPU_COUNT" -ge 2 ]; then
            TENSOR_PARALLEL_SIZE=2
            DISTRIBUTED_BACKEND="ray"
            echo "Mode: Auto-detected multi-node (2 GPUs)"
        else
            TENSOR_PARALLEL_SIZE=1
            DISTRIBUTED_BACKEND="mp"
            echo "Mode: Auto-detected single GPU"
        fi
    fi
    
    echo "Tensor Parallel Size: $TENSOR_PARALLEL_SIZE"
    echo "Distributed Backend: $DISTRIBUTED_BACKEND"
    echo ""
    echo "Press Ctrl+C to stop server"
    echo ""
    
    # Build and run command
    python -m vllm.entrypoints.openai.api_server \
        --model "$model" \
        --tensor-parallel-size $TENSOR_PARALLEL_SIZE \
        --pipeline-parallel-size 1 \
        --max-model-len 2048 \
        --port $VLLM_PORT \
        --host 0.0.0.0 \
        --trust-remote-code \
        --enforce-eager \
        --gpu-memory-utilization 0.8 \
        --disable-log-stats \
        --distributed-executor-backend $DISTRIBUTED_BACKEND
}

# Function to test server
test_server() {
    local test_port=${1:-$VLLM_PORT}
    local test_node=${2:-$CURRENT_NODE}
    
    echo ""
    echo "Testing vLLM Server"
    echo "=================="
    
    if [ "$test_node" = "node1" ]; then
        TEST_EXTERNAL_IP="$NODE1_EXTERNAL_IP"
    else
        TEST_EXTERNAL_IP="$NODE2_EXTERNAL_IP"
    fi
    
    echo "Testing port: $test_port"
    echo "External IP: $TEST_EXTERNAL_IP"
    
    # Test internal endpoint
    echo "Testing internal endpoint..."
    INTERNAL_URL="http://localhost:$test_port"
    
    # Wait for server
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s "$INTERNAL_URL/health" > /dev/null 2>&1; then
            echo "✓ Internal server is ready!"
            break
        fi
        echo "Waiting... ($i/30)"
        sleep 2
    done
    
    # Test completion
    echo "Testing completion endpoint..."
    RESPONSE=$(curl -s -X POST "$INTERNAL_URL/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "model",
            "prompt": "Hello from dual node setup!",
            "max_tokens": 30,
            "temperature": 0.7
        }')
    
    if [ $? -eq 0 ]; then
        echo "✓ Internal server test successful!"
        echo "Response preview:"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | head -10 || echo "$RESPONSE"
    else
        echo "✗ Internal server test failed"
    fi
    
    echo ""
    echo "Access Information:"
    echo "=================="
    echo "Internal: http://localhost:$test_port/v1/completions"
    echo "External: http://$TEST_EXTERNAL_IP:$test_port/v1/completions"
    echo ""
    echo "Test dari external dengan:"
    echo "curl -X POST http://$TEST_EXTERNAL_IP:$test_port/v1/completions \\"
    echo '  -H "Content-Type: application/json" \'
    echo '  -d '\''{"model": "model", "prompt": "Hello!", "max_tokens": 50}'\'''
}

# Main script
case "${1:-help}" in
    "deploy")
        MODEL=${2:-$DEFAULT_MODEL}
        MODE=${3:-"auto"}  # auto, multi, single
        
        show_config
        detect_node
        
        if [ "$CURRENT_NODE" = "node1" ]; then
            select_port 10808
        else
            select_port 20115
        fi
        
        setup_environment
        check_ray_cluster
        run_vllm "$MODEL" "$MODE"
        ;;
    "test")
        NODE=${2:-"auto"}
        PORT=${3:-"auto"}
        
        if [ "$NODE" = "auto" ]; then
            detect_node
        else
            CURRENT_NODE="$NODE"
            if [ "$NODE" = "node1" ]; then
                EXTERNAL_IP="$NODE1_EXTERNAL_IP"
            else
                EXTERNAL_IP="$NODE2_EXTERNAL_IP"
            fi
        fi
        
        if [ "$PORT" = "auto" ]; then
            if [ "$CURRENT_NODE" = "node1" ]; then
                VLLM_PORT=10808
            else
                VLLM_PORT=20115
            fi
        else
            VLLM_PORT="$PORT"
        fi
        
        test_server "$VLLM_PORT" "$CURRENT_NODE"
        ;;
    "status")
        show_config
        check_ray_cluster
        echo ""
        echo "Node Detection:"
        detect_node
        ;;
    "help"|*)
        echo "Usage:"
        echo "  $0 deploy [model] [mode]              # Deploy vLLM server"
        echo "  $0 test [node] [port]                 # Test server"
        echo "  $0 status                             # Show status"
        echo ""
        echo "Parameters:"
        echo "  model: Model name (default: $DEFAULT_MODEL)"
        echo "  mode:  auto/multi/single (default: auto)"
        echo "  node:  node1/node2/auto (default: auto)"
        echo "  port:  Port number (default: auto-select)"
        echo ""
        echo "Examples:"
        echo "  # Deploy dengan auto-detection"
        echo "  $0 deploy"
        echo ""
        echo "  # Deploy model specific dengan mode multi-node"
        echo "  $0 deploy Qwen/Qwen2.5-7B-Instruct multi"
        echo ""
        echo "  # Test node1 pada port 10808"
        echo "  $0 test node1 10808"
        echo ""
        echo "  # Test node2 dengan port default"
        echo "  $0 test node2"
        echo ""
        echo "Setup Summary:"
        echo "  Node 1: $NODE1_EXTERNAL_IP:$NODE1_PORTS"
        echo "  Node 2: $NODE2_EXTERNAL_IP:$NODE2_PORTS"
        echo "  Recommended ports: 10808 (node1), 20115 (node2)"
        ;;
esac