# Connect dan deploy ke Ray cluster
uv run python ray_model_deployer.py --ray-address 10.21.73.122:6379 --model "Qwen/Qwen2.5-0.5B-Instruct"

# Atau untuk auto-detect local cluster
uv run python ray_model_deployer.py --model "Qwen/Qwen2.5-0.5B-Instruct"

# Check status deployment
uv run python ray_model_deployer.py --action status

# Stop deployment
uv run python ray_model_deployer.py --action stop