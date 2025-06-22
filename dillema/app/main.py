from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dillema.ray.main import RayContainer

app = FastAPI()
ray_container = RayContainer()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    gpu_options = ["NVIDIA A100", "RTX 4090", "No GPU"]
    cpu_options = ["AMD Ryzen 9", "Intel i9"]
    nodes = [
        {"name": "Node 1", "gpu": "NVIDIA A100", "cpu": "AMD Ryzen 9", "hostname": "node1.example.com"},
        {"name": "Node 2", "gpu": "RTX 4090", "cpu": "Intel i9", "hostname": "node1.example.com"},
        {"name": "Node 3", "gpu": "No GPU", "cpu": "AMD Ryzen 9", "hostname": "node1.example.com"},
        {"name": "Node 3", "gpu": "No GPU", "cpu": "AMD Ryzen 9", "hostname": "node1.example.com"},
        {"name": "Node 3", "gpu": "No GPU", "cpu": "AMD Ryzen 9", "hostname": "node1.example.com"},
        {"name": "Node 3", "gpu": "No GPU", "cpu": "AMD Ryzen 9", "hostname": "node1.example.com"}
    ]
    return templates.TemplateResponse("index.html",    {
        "request": request,
        "gpu_options": gpu_options,
        "cpu_options": cpu_options,
        "nodes": nodes
    })

class ServeRequest(BaseModel):
    model_name: str
    gpu: str
    cpu: str

@app.post("/serve")
async def serve_model(req: ServeRequest):
    print(f"Serving model '{req.model_name}' on {req.gpu} + {req.cpu}")
    return {"status": "success", "message": f"Model '{req.model_name}' is being served on {req.gpu} + {req.cpu}"}