#!/bin/bash
# OpenVPN Multi-Node Network Setup
# Membuat internal network untuk Ray cluster communication

echo "OpenVPN Multi-Node Network Setup"
echo "================================"
echo "Creating internal network for:"
echo "  Node 1 (Head): 70.62.164.140    → VPN IP: 10.8.0.1"
echo "  Node 2 (Worker): 216.234.102.170 → VPN IP: 10.8.0.2"
echo ""

# Configuration
VPN_NETWORK="10.8.0.0"
VPN_NETMASK="255.255.255.0"
VPN_PORT="1194"
HEAD_NODE_VPN_IP="10.8.0.1"
WORKER_NODE_VPN_IP="10.8.0.2"

# Head node (server) configuration
HEAD_NODE_EXTERNAL="70.62.164.140"
WORKER_NODE_EXTERNAL="216.234.102.170"

# Function to show network architecture
show_vpn_architecture() {
    echo "VPN Network Architecture:"
    echo "========================"
    echo ""
    echo "Before (External IPs):"
    echo "  Node 1: 70.62.164.140     ←→     Node 2: 216.234.102.170"
    echo "  (Different Networks)              (Different Networks)"
    echo "  High Latency                      Firewall Issues"
    echo ""
    echo "After (VPN Internal):"
    echo "  Node 1: 10.8.0.1         ←→     Node 2: 10.8.0.2"
    echo "  (Same VPN Network)               (Same VPN Network)"
    echo "  Low Latency                      Secure Tunnel"
    echo ""
    echo "Benefits:"
    echo "  ✅ Internal IP communication"
    echo "  ✅ Encrypted traffic"
    echo "  ✅ Low latency"
    echo "  ✅ Simple Ray cluster setup"
    echo "  ✅ No complex port forwarding"
    echo ""
}

# Function to install OpenVPN
install_openvpn() {
    echo "Installing OpenVPN..."
    
    # Detect OS
    if [ -f /etc/debian_version ]; then
        echo "Detected Debian/Ubuntu system"
        sudo apt update
        sudo apt install -y openvpn easy-rsa
    elif [ -f /etc/redhat-release ]; then
        echo "Detected RedHat/CentOS system"
        sudo yum install -y epel-release
        sudo yum install -y openvpn easy-rsa
    else
        echo "Please install OpenVPN manually for your OS"
        exit 1
    fi
    
    echo "✅ OpenVPN installed"
}

# Function to setup PKI (Public Key Infrastructure)
setup_pki() {
    echo "Setting up PKI (Certificate Authority)..."
    
    # Create PKI directory
    PKI_DIR="$HOME/openvpn-pki"
    mkdir -p $PKI_DIR
    cd $PKI_DIR
    
    # Copy easy-rsa
    if [ -d /usr/share/easy-rsa ]; then
        cp -r /usr/share/easy-rsa/* .
    elif [ -d /etc/easy-rsa ]; then
        cp -r /etc/easy-rsa/* .
    else
        echo "Easy-RSA not found, downloading..."
        wget https://github.com/OpenVPN/easy-rsa/releases/download/v3.1.0/EasyRSA-3.1.0.tgz
        tar xzf EasyRSA-3.1.0.tgz
        mv EasyRSA-3.1.0/* .
    fi
    
    # Initialize PKI
    echo "Initializing PKI..."
    ./easyrsa init-pki
    
    # Build CA (Certificate Authority)
    echo "Building CA..."
    echo -e "\n\n\n\n\n\nRay-Cluster-CA\n" | ./easyrsa build-ca nopass
    
    # Generate server certificate
    echo "Generating server certificate..."
    echo -e "\n\n\n\n\n\n\n" | ./easyrsa build-server-full ray-head nopass
    
    # Generate client certificate
    echo "Generating client certificate..."
    echo -e "\n\n\n\n\n\n\n" | ./easyrsa build-client-full ray-worker nopass
    
    # Generate Diffie-Hellman parameters
    echo "Generating DH parameters..."
    ./easyrsa gen-dh
    
    # Generate TLS auth key
    echo "Generating TLS auth key..."
    openvpn --genkey secret pki/ta.key
    
    echo "✅ PKI setup completed"
    echo "📁 Certificates location: $PKI_DIR/pki"
}

# Function to create server configuration
create_server_config() {
    echo "Creating OpenVPN server configuration..."
    
    SERVER_CONFIG="/etc/openvpn/server/ray-cluster.conf"
    sudo mkdir -p /etc/openvpn/server
    
    sudo tee $SERVER_CONFIG > /dev/null <<EOF
# OpenVPN Server Configuration for Ray Cluster
port $VPN_PORT
proto udp
dev tun

# Certificates and keys
ca $PKI_DIR/pki/ca.crt
cert $PKI_DIR/pki/issued/ray-head.crt
key $PKI_DIR/pki/private/ray-head.key
dh $PKI_DIR/pki/dh.pem
tls-auth $PKI_DIR/pki/ta.key 0

# Network configuration
server $VPN_NETWORK $VPN_NETMASK
ifconfig-pool-persist /var/log/openvpn/ipp.txt

# Client specific configuration
client-config-dir /etc/openvpn/ccd
route $VPN_NETWORK $VPN_NETMASK

# Security
cipher AES-256-GCM
auth SHA256
tls-version-min 1.2

# Other settings
keepalive 10 120
comp-lzo
persist-key
persist-tun
status /var/log/openvpn/status.log
log-append /var/log/openvpn/openvpn.log
verb 3
explicit-exit-notify 1

# Performance optimization for Ray
sndbuf 393216
rcvbuf 393216
push "sndbuf 393216"
push "rcvbuf 393216"

# MTU optimization
tun-mtu 1500
mssfix 1460
EOF

    # Create client config directory
    sudo mkdir -p /etc/openvpn/ccd
    
    # Create client-specific config for worker node
    sudo tee /etc/openvpn/ccd/ray-worker > /dev/null <<EOF
ifconfig-push $WORKER_NODE_VPN_IP $HEAD_NODE_VPN_IP
EOF

    # Create log directory
    sudo mkdir -p /var/log/openvpn
    
    echo "✅ Server configuration created"
    echo "📄 Config file: $SERVER_CONFIG"
}

# Function to create client configuration
create_client_config() {
    echo "Creating OpenVPN client configuration..."
    
    CLIENT_CONFIG="$PKI_DIR/ray-worker.ovpn"
    
    cat > $CLIENT_CONFIG <<EOF
# OpenVPN Client Configuration for Ray Worker
client
dev tun
proto udp
remote $HEAD_NODE_EXTERNAL $VPN_PORT
resolv-retry infinite
nobind
persist-key
persist-tun

# Security
cipher AES-256-GCM
auth SHA256
tls-version-min 1.2
remote-cert-tls server

# Performance
comp-lzo
verb 3

# MTU optimization
tun-mtu 1500
mssfix 1460

# Inline certificates and keys
<ca>
$(cat $PKI_DIR/pki/ca.crt)
</ca>

<cert>
$(cat $PKI_DIR/pki/issued/ray-worker.crt)
</cert>

<key>
$(cat $PKI_DIR/pki/private/ray-worker.key)
</key>

<tls-auth>
$(cat $PKI_DIR/pki/ta.key)
</tls-auth>
key-direction 1
EOF

    echo "✅ Client configuration created"
    echo "📄 Client config: $CLIENT_CONFIG"
    echo ""
    echo "📋 Next steps:"
    echo "1. Copy $CLIENT_CONFIG to Node 2 (216.234.102.170)"
    echo "2. Install and run OpenVPN client on Node 2"
}

# Function to enable IP forwarding and firewall
configure_firewall() {
    echo "Configuring firewall and IP forwarding..."
    
    # Enable IP forwarding
    echo "Enabling IP forwarding..."
    echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.conf
    sudo sysctl -p
    
    # Configure iptables for OpenVPN
    echo "Configuring iptables..."
    
    # Allow OpenVPN port
    sudo iptables -A INPUT -p udp --dport $VPN_PORT -j ACCEPT
    
    # Allow VPN traffic
    sudo iptables -A INPUT -i tun+ -j ACCEPT
    sudo iptables -A FORWARD -i tun+ -j ACCEPT
    sudo iptables -A FORWARD -i tun+ -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
    sudo iptables -A FORWARD -i eth0 -o tun+ -m state --state RELATED,ESTABLISHED -j ACCEPT
    
    # NAT for VPN clients
    sudo iptables -t nat -A POSTROUTING -s $VPN_NETWORK/24 -o eth0 -j MASQUERADE
    
    # Save iptables rules
    if command -v netfilter-persistent > /dev/null; then
        sudo netfilter-persistent save
    elif command -v iptables-save > /dev/null; then
        sudo iptables-save | sudo tee /etc/iptables/rules.v4
    fi
    
    echo "✅ Firewall configured"
}

# Function to start OpenVPN server
start_openvpn_server() {
    echo "Starting OpenVPN server..."
    
    # Start and enable OpenVPN service
    sudo systemctl start openvpn-server@ray-cluster
    sudo systemctl enable openvpn-server@ray-cluster
    
    # Check status
    sleep 3
    if sudo systemctl is-active --quiet openvpn-server@ray-cluster; then
        echo "✅ OpenVPN server started successfully"
        
        # Show server status
        echo ""
        echo "🔍 Server Status:"
        sudo systemctl status openvpn-server@ray-cluster --no-pager -l
        
        # Show VPN interface
        echo ""
        echo "🔍 VPN Interface:"
        ip addr show tun0 2>/dev/null || echo "TUN interface not yet created"
        
    else
        echo "❌ OpenVPN server failed to start"
        echo "Check logs with: sudo journalctl -u openvpn-server@ray-cluster -f"
        return 1
    fi
}

# Function to create installation script for worker node
create_worker_setup_script() {
    echo "Creating setup script for worker node..."
    
    WORKER_SCRIPT="$PKI_DIR/setup-worker-node.sh"
    
    cat > $WORKER_SCRIPT <<'EOF'
#!/bin/bash
# Worker Node OpenVPN Setup Script
# Run this script on Node 2 (216.234.102.170)

echo "Setting up OpenVPN client on worker node..."

# Install OpenVPN client
if [ -f /etc/debian_version ]; then
    sudo apt update
    sudo apt install -y openvpn
elif [ -f /etc/redhat-release ]; then
    sudo yum install -y epel-release
    sudo yum install -y openvpn
fi

# Copy client config to OpenVPN directory
sudo cp ray-worker.ovpn /etc/openvpn/client/

# Start OpenVPN client
sudo systemctl start openvpn-client@ray-worker
sudo systemctl enable openvpn-client@ray-worker

# Check connection
sleep 5
if ip addr show tun0 &>/dev/null; then
    echo "✅ VPN connection established"
    echo "VPN IP: $(ip addr show tun0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)"
    
    # Test connection to head node
    echo "Testing connection to head node..."
    if ping -c 3 10.8.0.1; then
        echo "✅ Can reach head node via VPN"
    else
        echo "❌ Cannot reach head node"
    fi
else
    echo "❌ VPN connection failed"
    echo "Check logs: sudo journalctl -u openvpn-client@ray-worker -f"
fi
EOF

    chmod +x $WORKER_SCRIPT
    
    echo "✅ Worker setup script created: $WORKER_SCRIPT"
}

# Function to test VPN connection
test_vpn_connection() {
    echo "Testing VPN connection..."
    
    # Check if TUN interface exists
    if ip addr show tun0 &>/dev/null; then
        VPN_IP=$(ip addr show tun0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1)
        echo "✅ VPN interface active"
        echo "   Head node VPN IP: $VPN_IP"
        
        # Test if we can ping worker (if connected)
        echo "Testing connection to worker node..."
        if ping -c 2 -W 2 $WORKER_NODE_VPN_IP &>/dev/null; then
            echo "✅ Worker node reachable via VPN"
        else
            echo "⏳ Worker node not yet connected (normal if worker not setup)"
        fi
        
    else
        echo "❌ VPN interface not found"
        echo "Check OpenVPN server status"
    fi
}

# Function to create Ray cluster setup after VPN
create_ray_vpn_setup() {
    echo "Creating Ray cluster setup for VPN network..."
    
    RAY_SETUP_SCRIPT="$PKI_DIR/ray-cluster-vpn.sh"
    
    cat > $RAY_SETUP_SCRIPT <<EOF
#!/bin/bash
# Ray Cluster Setup untuk VPN Network

echo "Ray Cluster Setup via VPN"
echo "========================="

# Check VPN connection
if ! ip addr show tun0 &>/dev/null; then
    echo "❌ VPN not connected. Setup VPN first."
    exit 1
fi

VPN_IP=\$(ip addr show tun0 | grep 'inet ' | awk '{print \$2}' | cut -d'/' -f1)
echo "Current VPN IP: \$VPN_IP"

# Determine role based on VPN IP
if [ "\$VPN_IP" = "$HEAD_NODE_VPN_IP" ]; then
    echo "🎯 Setting up Ray HEAD node"
    
    # Stop existing Ray
    ray stop 2>/dev/null
    
    # Start Ray head dengan VPN IP
    ray start --head \\
        --port=6379 \\
        --node-ip-address=$HEAD_NODE_VPN_IP \\
        --dashboard-host=$HEAD_NODE_VPN_IP \\
        --dashboard-port=8265
    
    echo "✅ Ray head started"
    echo "   VPN IP: $HEAD_NODE_VPN_IP:6379"
    echo "   Dashboard: http://$HEAD_NODE_VPN_IP:8265"
    echo "   Worker command: ray start --address=$HEAD_NODE_VPN_IP:6379"

elif [ "\$VPN_IP" = "$WORKER_NODE_VPN_IP" ]; then
    echo "🎯 Setting up Ray WORKER node"
    
    # Stop existing Ray
    ray stop 2>/dev/null
    
    # Connect to head node via VPN
    ray start --address=$HEAD_NODE_VPN_IP:6379
    
    echo "✅ Ray worker connected"
    echo "   Connected to: $HEAD_NODE_VPN_IP:6379"

else
    echo "❌ Unknown VPN IP: \$VPN_IP"
    exit 1
fi

# Show Ray status
echo ""
echo "🔍 Ray Cluster Status:"
ray status
EOF

    chmod +x $RAY_SETUP_SCRIPT
    
    echo "✅ Ray VPN setup script created: $RAY_SETUP_SCRIPT"
}

# Function to create vLLM deployment script for VPN
create_vllm_vpn_script() {
    echo "Creating vLLM deployment script for VPN..."
    
    VLLM_SCRIPT="$PKI_DIR/vllm-deploy-vpn.sh"
    
    cat > $VLLM_SCRIPT <<EOF
#!/bin/bash
# vLLM Deployment via VPN Network

MODEL=\${1:-"Qwen/Qwen2.5-1.5B-Instruct"}
PORT=\${2:-8000}

echo "vLLM Deployment via VPN"
echo "======================="
echo "Model: \$MODEL"
echo "Port: \$PORT"

# Check if we're on head node
VPN_IP=\$(ip addr show tun0 | grep 'inet ' | awk '{print \$2}' | cut -d'/' -f1)
if [ "\$VPN_IP" != "$HEAD_NODE_VPN_IP" ]; then
    echo "❌ vLLM harus dijalankan di head node ($HEAD_NODE_VPN_IP)"
    exit 1
fi

# Check Ray cluster
echo "🔍 Checking Ray cluster..."
if ! ray status | grep -q "GPU"; then
    echo "❌ Ray cluster tidak ready atau tidak ada GPU"
    echo "Run: $RAY_SETUP_SCRIPT"
    exit 1
fi

# Setup environment
export CUDA_LAUNCH_BLOCKING=0
export NCCL_DEBUG=WARN
export NCCL_SOCKET_IFNAME=tun0
export VLLM_HOST_IP=$HEAD_NODE_VPN_IP

# Deploy vLLM
echo "🚀 Starting vLLM server..."
echo "   VPN Network: Internal communication"
echo "   Binding to: $HEAD_NODE_VPN_IP:\$PORT"
echo ""

python -m vllm.entrypoints.openai.api_server \\
    --model "\$MODEL" \\
    --tensor-parallel-size 2 \\
    --pipeline-parallel-size 1 \\
    --max-model-len 2048 \\
    --port \$PORT \\
    --host $HEAD_NODE_VPN_IP \\
    --trust-remote-code \\
    --enforce-eager \\
    --gpu-memory-utilization 0.8 \\
    --distributed-executor-backend ray
EOF

    chmod +x $VLLM_SCRIPT
    
    echo "✅ vLLM VPN deployment script created: $VLLM_SCRIPT"
}

# Main setup function
main() {
    case "${1:-help}" in
        "install")
            install_openvpn
            ;;
        "setup-server")
            echo "Setting up OpenVPN server (Head Node)..."
            show_vpn_architecture
            install_openvpn
            setup_pki
            create_server_config
            configure_firewall
            start_openvpn_server
            create_client_config
            create_worker_setup_script
            create_ray_vpn_setup
            create_vllm_vpn_script
            test_vpn_connection
            
            echo ""
            echo "🎉 HEAD NODE SETUP COMPLETED!"
            echo "================================"
            echo ""
            echo "📋 Next Steps:"
            echo "1. Copy these files to Node 2 (216.234.102.170):"
            echo "   - $PKI_DIR/ray-worker.ovpn"
            echo "   - $PKI_DIR/setup-worker-node.sh"
            echo ""
            echo "2. SSH to Node 2 and run:"
            echo "   chmod +x setup-worker-node.sh"
            echo "   ./setup-worker-node.sh"
            echo ""
            echo "3. After VPN connected, setup Ray cluster:"
            echo "   Head Node: $PKI_DIR/ray-cluster-vpn.sh"
            echo "   Worker Node: $PKI_DIR/ray-cluster-vpn.sh"
            echo ""
            echo "4. Deploy vLLM (on head node):"
            echo "   $PKI_DIR/vllm-deploy-vpn.sh"
            echo ""
            ;;
        "test")
            test_vpn_connection
            ;;
        "status")
            echo "OpenVPN Server Status:"
            sudo systemctl status openvpn-server@ray-cluster --no-pager
            echo ""
            echo "VPN Interface:"
            ip addr show tun0 2>/dev/null || echo "TUN interface not found"
            echo ""
            echo "Connected Clients:"
            sudo cat /var/log/openvpn/status.log 2>/dev/null | grep "CLIENT_LIST" || echo "No status file"
            ;;
        "logs")
            echo "OpenVPN Server Logs:"
            sudo journalctl -u openvpn-server@ray-cluster -f
            ;;
        "help"|*)
            show_vpn_architecture
            echo "Usage:"
            echo "  $0 setup-server          # Setup OpenVPN server (run on Head Node)"
            echo "  $0 test                  # Test VPN connection"
            echo "  $0 status                # Show VPN status"
            echo "  $0 logs                  # Show VPN logs"
            echo ""
            echo "Setup Process:"
            echo "1. Run on Head Node (70.62.164.140):"
            echo "   $0 setup-server"
            echo ""
            echo "2. Copy files to Worker Node (216.234.102.170)"
            echo ""
            echo "3. Run setup on Worker Node"
            echo ""
            echo "4. Setup Ray cluster via VPN"
            echo ""
            echo "5. Deploy vLLM"
            echo ""
            echo "Benefits of VPN Setup:"
            echo "  ✅ Internal network (10.8.0.x)"
            echo "  ✅ Encrypted communication"
            echo "  ✅ Low latency"
            echo "  ✅ Simple Ray configuration"
            echo "  ✅ No complex port forwarding"
            ;;
    esac
}

main "$@"