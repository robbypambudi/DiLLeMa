import argparse
import uvicorn
import ray

def serve_model(args):
    """
    Serve model via FastAPI server
    """
    ray.init(address="auto")
    print("Menjalankan server FastAPI...")

def main():
    parser = argparse.ArgumentParser(description="Run the Dillema API server")
    subparsers = parser.add_subparsers()
    
     # Subcommand untuk serve model via API
    serve_parser = subparsers.add_parser("serve", help="Serve model via FastAPI")
    serve_parser.add_argument("--model", type=str, required=True, help="Nama model atau path model")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port untuk API server")
    serve_parser.set_defaults(func=serve_model)

if __name__ == "__main__":
    main()