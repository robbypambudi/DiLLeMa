# Connect dan deploy ke Ray cluster
python ray_model_deployer.py --ray-address 10.21.73.122:6379 --model "Qwen/Qwen2.5-0.5B-Instruct"

# Atau untuk auto-detect local cluster
python ray_model_deployer.py --model "Qwen/Qwen2.5-0.5B-Instruct"

# Check status deployment
python ray_model_deployer.py --action status

# Stop deployment
python ray_model_deployer.py --action stop