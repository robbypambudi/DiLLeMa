#!/usr/bin/env python3
"""
Cross-Network Multi-Node Setup
Setup untuk vLLM multi-node dengan external IP communication
"""

import subprocess
import os
import sys
import time
import logging
import json
import socket

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Cross-network node configuration
NODES = {
    "node1": {
        "external_ip": "216.234.102.170",
        "ssh_port": 10803,
        "ray_ports": {
            "head_port": 10806,      # Ray head port
            "dashboard_port": 10807,  # Ray dashboard
            "object_store": 10808,    # Ray object store
            "worker_ports": [10809, 10810, 10811]  # Additional Ray worker ports
        },
        "vllm_port": 10815,         # vLLM API port
        "role": "head"
    },
    "node2": {
        "external_ip": "70.62.164.140", 
        "ssh_port": 20100,
        "ray_ports": {
            "worker_port": 20109,     # Ray worker connection port
            "object_store": 20110,    # Ray object store
            "additional_ports": [20111, 20112, 20113]  # Additional Ray ports
        },
        "role": "worker"
    }
}

def show_cross_network_overview():
    """Show cross-network setup overview"""
    print("=" * 70)
    print("CROSS-NETWORK MULTI-NODE vLLM SETUP")
    print("=" * 70)
    print()
    print("Network Architecture:")
    print("  Node 1 (Head)              Node 2 (Worker)")
    print("  216.234.102.170     ←→     70.62.164.140")
    print("  (Different Networks)       (Different Networks)")
    print("  RTX 4090 (24GB)            RTX 4090 (24GB)")
    print("        ↓                           ↓")
    print("   Ray Head Server            Ray Worker Client")
    print("   (External IP Bind)         (Connect via External)")
    print()
    print("Key Differences dari Internal Network:")
    print("❌ TIDAK ada internal network 192.168.x.x communication")
    print("✅ Ray communication via EXTERNAL IP")
    print("✅ Port forwarding untuk Ray ports")
    print("✅ Firewall/NAT harus allow Ray traffic")
    print()
    print("Required Ports:")
    print("  Node 1: 10806 (Ray head), 10807 (dashboard), 10808+ (workers)")
    print("  Node 2: 20109+ (Ray worker ports)")
    print()

def get_current_external_ip():
    """Get current node's external IP"""
    try:
        # Try to detect based on available method
        # In production, this might be configured
        
        # For now, let's ask user since detection is complex
        print("Available nodes:")
        print("1) Node 1 (216.234.102.170)")
        print("2) Node 2 (70.62.164.140)")
        choice = input("Which node are you currently on? (1/2): ").strip()
        
        if choice == "1":
            return "node1", NODES["node1"]["external_ip"]
        elif choice == "2":
            return "node2", NODES["node2"]["external_ip"]
        else:
            logger.error("Invalid choice")
            return None, None
            
    except Exception as e:
        logger.error(f"Error detecting node: {e}")
        return None, None

def setup_ray_head_external(external_ip, ports):
    """Setup Ray head dengan external IP binding"""
    logger.info("=" * 60)
    logger.info("SETTING UP RAY HEAD (EXTERNAL IP MODE)")
    logger.info("=" * 60)
    
    head_port = ports["head_port"]
    dashboard_port = ports["dashboard_port"]
    
    logger.info(f"External IP: {external_ip}")
    logger.info(f"Head port: {head_port}")
    logger.info(f"Dashboard port: {dashboard_port}")
    
    # Stop any existing Ray
    logger.info("Stopping existing Ray processes...")
    subprocess.run(['ray', 'stop'], capture_output=True)
    time.sleep(3)
    
    # Build Ray head command dengan external IP
    cmd = [
        'ray', 'start',
        '--head',
        f'--port={head_port}',
        f'--node-ip-address={external_ip}',  # Bind to external IP
        f'--dashboard-host={external_ip}',    # Dashboard on external IP
        f'--dashboard-port={dashboard_port}',
        '--verbose'
    ]
    
    logger.info("Ray head command:")
    logger.info(" ".join(cmd))
    logger.info("")
    
    try:
        # Set environment for external networking
        env = os.environ.copy()
        env.update({
            'RAY_DISABLE_IMPORT_WARNING': '1',
            'RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER': '1',  # Allow cross-platform
            'RAY_SCHEDULER_EVENTS': '0',
        })
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        
        if result.returncode == 0:
            logger.info("✅ Ray head started successfully!")
            logger.info(result.stdout)
            
            # Save connection info for worker
            connection_info = {
                "head_ip": external_ip,
                "head_port": head_port,
                "dashboard_url": f"http://{external_ip}:{dashboard_port}",
                "worker_connect_address": f"{external_ip}:{head_port}",
                "timestamp": time.time(),
                "setup_type": "cross_network"
            }
            
            with open("ray_cross_network_info.json", "w") as f:
                json.dump(connection_info, f, indent=2)
            
            logger.info("")
            logger.info("🎯 Connection Information:")
            logger.info(f"   Ray Head: {external_ip}:{head_port}")
            logger.info(f"   Dashboard: http://{external_ip}:{dashboard_port}")
            logger.info(f"   Worker Command: ray start --address={external_ip}:{head_port}")
            logger.info("")
            
            return True
        else:
            logger.error("❌ Failed to start Ray head")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Ray head startup timeout")
        return False
    except Exception as e:
        logger.error(f"❌ Ray head setup error: {e}")
        return False

def setup_ray_worker_external(head_ip, head_port, worker_external_ip=None):
    """Setup Ray worker untuk connect ke external head"""
    logger.info("=" * 60)
    logger.info("SETTING UP RAY WORKER (EXTERNAL CONNECT)")
    logger.info("=" * 60)
    
    logger.info(f"Connecting to head: {head_ip}:{head_port}")
    if worker_external_ip:
        logger.info(f"Worker external IP: {worker_external_ip}")
    
    # Stop existing Ray
    logger.info("Stopping existing Ray processes...")
    subprocess.run(['ray', 'stop'], capture_output=True)
    time.sleep(3)
    
    # Build worker command
    cmd = [
        'ray', 'start',
        f'--address={head_ip}:{head_port}',
    ]
    
    if worker_external_ip:
        cmd.extend([f'--node-ip-address={worker_external_ip}'])
    
    cmd.append('--verbose')
    
    logger.info("Ray worker command:")
    logger.info(" ".join(cmd))
    logger.info("")
    
    try:
        env = os.environ.copy()
        env.update({
            'RAY_DISABLE_IMPORT_WARNING': '1',
            'RAY_ENABLE_WINDOWS_OR_OSX_CLUSTER': '1',
        })
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        
        if result.returncode == 0:
            logger.info("✅ Ray worker connected successfully!")
            logger.info(result.stdout)
            return True
        else:
            logger.error("❌ Ray worker connection failed")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            
            # Common issues troubleshooting
            if "Connection refused" in result.stderr:
                logger.error("🔍 Troubleshooting: Connection refused")
                logger.error("   - Check if Ray head is running")
                logger.error("   - Check firewall/port forwarding")
                logger.error(f"   - Test: telnet {head_ip} {head_port}")
            
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ Ray worker connection timeout")
        return False
    except Exception as e:
        logger.error(f"❌ Ray worker setup error: {e}")
        return False

def test_cross_network_connectivity(target_ip, target_port):
    """Test network connectivity antara nodes"""
    logger.info(f"🔍 Testing connectivity to {target_ip}:{target_port}")
    
    try:
        # Test dengan socket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((target_ip, target_port))
        sock.close()
        
        if result == 0:
            logger.info(f"✅ Port {target_port} is accessible on {target_ip}")
            return True
        else:
            logger.error(f"❌ Port {target_port} is NOT accessible on {target_ip}")
            logger.error("🔍 Possible issues:")
            logger.error("   - Port tidak di-forward")
            logger.error("   - Firewall blocking")
            logger.error("   - Ray head belum start")
            return False
            
    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False

def deploy_vllm_cross_network(model, external_ip, vllm_port, max_len=2048):
    """Deploy vLLM dengan cross-network Ray cluster"""
    logger.info("=" * 60)
    logger.info("DEPLOYING vLLM (CROSS-NETWORK MODE)")
    logger.info("=" * 60)
    
    logger.info(f"Model: {model}")
    logger.info(f"External IP: {external_ip}")
    logger.info(f"vLLM Port: {vllm_port}")
    
    # Check Ray cluster first
    try:
        result = subprocess.run(['ray', 'status'], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.error("❌ Ray cluster not accessible")
            return False
        
        logger.info("Ray cluster status:")
        print(result.stdout)
        
        # Check for multiple GPUs
        if "GPU" not in result.stdout:
            logger.error("❌ No GPU resources in cluster")
            return False
        
        # Try to detect GPU count
        gpu_lines = [line for line in result.stdout.split('\n') if 'GPU' in line]
        logger.info(f"GPU resources detected: {gpu_lines}")
        
    except Exception as e:
        logger.error(f"❌ Ray status check failed: {e}")
        return False
    
    # Setup environment for cross-network
    logger.info("Setting up cross-network environment...")
    
    env_vars = {
        'CUDA_LAUNCH_BLOCKING': '0',
        'NCCL_DEBUG': 'INFO',
        'VLLM_WORKER_MULTIPROC_METHOD': 'spawn',
        'RAY_DISABLE_IMPORT_WARNING': '1',
        # Cross-network specific
        'NCCL_IB_DISABLE': '1',           # Disable InfiniBand
        'NCCL_P2P_DISABLE': '1',          # Disable P2P
        'NCCL_SOCKET_NTHREADS': '2',      # Reduce socket threads
        'NCCL_NSOCKS_PERTHREAD': '2',     # Reduce sockets per thread
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value
        logger.info(f"  {key}: {value}")
    
    # Build vLLM command
    cmd = [
        'python', '-m', 'vllm.entrypoints.openai.api_server',
        '--model', model,
        '--tensor-parallel-size', '2',  # Try 2 GPUs cross-network
        '--pipeline-parallel-size', '1',
        '--max-model-len', str(max_len),
        '--port', str(vllm_port),
        '--host', external_ip,  # Bind to external IP
        '--trust-remote-code',
        '--enforce-eager',
        '--gpu-memory-utilization', '0.8',
        '--disable-log-stats',
        '--distributed-executor-backend', 'ray',
    ]
    
    logger.info("vLLM cross-network command:")
    logger.info(" ".join(cmd))
    logger.info("")
    logger.info("🚀 Starting vLLM server...")
    logger.info("⚠️  Cross-network setup mungkin lambat untuk startup")
    logger.info("🌐 Server akan bind ke external IP")
    logger.info("")
    
    try:
        process = subprocess.run(cmd)
        return True
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping vLLM server...")
        return True
    except Exception as e:
        logger.error(f"❌ vLLM cross-network deployment failed: {e}")
        logger.info("🔄 Trying fallback to single GPU...")
        return deploy_vllm_single_fallback(model, external_ip, vllm_port, max_len)

def deploy_vllm_single_fallback(model, external_ip, vllm_port, max_len=2048):
    """Fallback ke single GPU jika cross-network multi-GPU gagal"""
    logger.info("=" * 60)
    logger.info("VLLM SINGLE GPU FALLBACK")
    logger.info("=" * 60)
    
    cmd = [
        'python', '-m', 'vllm.entrypoints.openai.api_server',
        '--model', model,
        '--tensor-parallel-size', '1',
        '--pipeline-parallel-size', '1',
        '--max-model-len', str(max_len),
        '--port', str(vllm_port),
        '--host', external_ip,
        '--trust-remote-code',
        '--enforce-eager',
        '--gpu-memory-utilization', '0.8',
        '--distributed-executor-backend', 'mp',  # Use multiprocessing
    ]
    
    logger.info("Single GPU fallback command:")
    logger.info(" ".join(cmd))
    
    try:
        process = subprocess.run(cmd)
        return True
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping fallback server...")
        return True
    except Exception as e:
        logger.error(f"❌ Single GPU fallback failed: {e}")
        return False

def show_node2_instructions(head_ip, head_port):
    """Show detailed instructions untuk setup Node 2"""
    node2_config = NODES["node2"]
    
    logger.info("=" * 70)
    logger.info("INSTRUKSI UNTUK NODE 2 SETUP")
    logger.info("=" * 70)
    logger.info("")
    logger.info("Node 2 harus setup sebagai Ray worker dengan external connection.")
    logger.info("")
    logger.info("1️⃣ SSH ke Node 2:")
    logger.info(f"   ssh -p {node2_config['ssh_port']} user@{node2_config['external_ip']}")
    logger.info("")
    logger.info("2️⃣ Di Node 2, jalankan Ray worker:")
    logger.info(f"   ray start --address={head_ip}:{head_port} --node-ip-address={node2_config['external_ip']}")
    logger.info("")
    logger.info("3️⃣ Verify connection di Node 2:")
    logger.info("   ray status")
    logger.info("")
    logger.info("4️⃣ Jika connection gagal, check connectivity:")
    logger.info(f"   telnet {head_ip} {head_port}")
    logger.info("")
    logger.info("5️⃣ Kembali ke Node 1 untuk deploy vLLM")
    logger.info("")
    logger.info("⚠️  PENTING: Pastikan port forwarding aktif!")
    logger.info(f"   Node 1 port {head_port} harus accessible dari Node 2")

def main():
    if len(sys.argv) < 2:
        show_cross_network_overview()
        print("Usage:")
        print("  python cross_network_multinode_setup.py setup-head")
        print("  python cross_network_multinode_setup.py setup-worker <head_ip> <head_port>")
        print("  python cross_network_multinode_setup.py test-connection <target_ip> <target_port>")
        print("  python cross_network_multinode_setup.py deploy <model> [port]")
        print("  python cross_network_multinode_setup.py auto-setup")
        print()
        print("Examples:")
        print("  # Auto setup dengan detection")
        print("  python cross_network_multinode_setup.py auto-setup")
        print()
        print("  # Setup head di Node 1")
        print("  python cross_network_multinode_setup.py setup-head")
        print()
        print("  # Setup worker di Node 2")
        print("  python cross_network_multinode_setup.py setup-worker 216.234.102.170 10806")
        print()
        print("  # Test connectivity")
        print("  python cross_network_multinode_setup.py test-connection 216.234.102.170 10806")
        print()
        print("  # Deploy vLLM")
        print("  python cross_network_multinode_setup.py deploy Qwen/Qwen2.5-1.5B-Instruct")
        return
    
    action = sys.argv[1]
    
    if action == "auto-setup":
        show_cross_network_overview()
        
        current_node, external_ip = get_current_external_ip()
        if not current_node:
            return
        
        if current_node == "node1":
            logger.info("🎯 Setting up Node 1 as Ray head...")
            ports = NODES["node1"]["ray_ports"]
            
            if setup_ray_head_external(external_ip, ports):
                show_node2_instructions(external_ip, ports["head_port"])
                
                input("\n⏳ Press Enter setelah Node 2 setup selesai...")
                
                # Test cluster
                logger.info("🔍 Testing Ray cluster...")
                try:
                    result = subprocess.run(['ray', 'status'], capture_output=True, text=True)
                    if "GPU" in result.stdout and "2.0" in result.stdout:
                        logger.info("✅ Cross-network cluster ready!")
                        logger.info("🚀 Siap deploy vLLM:")
                        logger.info(f"   python {sys.argv[0]} deploy Qwen/Qwen2.5-1.5B-Instruct")
                    else:
                        logger.warning("⚠️  Cluster belum optimal, check Node 2 connection")
                except:
                    logger.error("❌ Cluster check failed")
        
        elif current_node == "node2":
            logger.info("🎯 Node 2 detected.")
            head_ip = input("Enter Node 1 external IP [216.234.102.170]: ").strip() or "216.234.102.170"
            head_port = int(input("Enter Ray head port [10806]: ").strip() or "10806")
            
            # Test connectivity first
            if test_cross_network_connectivity(head_ip, head_port):
                logger.info("✅ Connectivity OK, setting up worker...")
                setup_ray_worker_external(head_ip, head_port, external_ip)
            else:
                logger.error("❌ Cannot connect to head node")
    
    elif action == "setup-head":
        current_node, external_ip = get_current_external_ip()
        if current_node == "node1":
            ports = NODES["node1"]["ray_ports"]
            setup_ray_head_external(external_ip, ports)
            show_node2_instructions(external_ip, ports["head_port"])
    
    elif action == "setup-worker":
        if len(sys.argv) < 4:
            logger.error("Usage: setup-worker <head_ip> <head_port>")
            return
        
        head_ip = sys.argv[2]
        head_port = int(sys.argv[3])
        current_node, external_ip = get_current_external_ip()
        
        if test_cross_network_connectivity(head_ip, head_port):
            setup_ray_worker_external(head_ip, head_port, external_ip)
        else:
            logger.error("Cannot establish connection to head")
    
    elif action == "test-connection":
        if len(sys.argv) < 4:
            logger.error("Usage: test-connection <target_ip> <target_port>")
            return
        
        target_ip = sys.argv[2]
        target_port = int(sys.argv[3])
        test_cross_network_connectivity(target_ip, target_port)
    
    elif action == "deploy":
        if len(sys.argv) < 3:
            logger.error("Usage: deploy <model> [port]")
            return
        
        model = sys.argv[2]
        current_node, external_ip = get_current_external_ip()
        
        if current_node == "node1":
            vllm_port = int(sys.argv[3]) if len(sys.argv) > 3 else NODES["node1"]["vllm_port"]
            deploy_vllm_cross_network(model, external_ip, vllm_port)
        else:
            logger.error("vLLM deployment harus dijalankan di Node 1 (head)")
    
    else:
        logger.error("Invalid action")

if __name__ == "__main__":
    main()