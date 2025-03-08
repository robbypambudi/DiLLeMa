# DiLLeMa

DiLLeMa is a distributed Large Language Model (LLM) that can be used to generate text. It is built on top of Ray Framework and VLLM. The purpose of this project is to provide a easy-to-use interface for users to deploy and use LLMs in a distributed setting.

![Architectural](/docs/assets/architecture.png)

## Installation

```bash
pip install dillema
```

## Project Structure

```
/dillema
│
├── api_gateway/                # API Layer (FastAPI)
│   ├── __init__.py
│   ├── main.py                 # Entry point untuk API
│   ├── endpoints.py            # Definisi endpoint API
│   └── utils.py                # Utility functions (e.g., request validation)
│
├── ray_cluster/                # Ray cluster manager & task scheduler
│   ├── __init__.py
│   ├── ray_manager.py          # Manajer cluster Ray
│   ├── task_scheduler.py       # Pembagian tugas ke worker
│   └── worker_manager.py       # Menangani pengelolaan worker Ray
│
├── workers/                    # Worker nodes yang menjalankan LLM inferensi
│   ├── __init__.py
│   ├── worker.py               # Kode untuk setiap worker (Actor Ray)
│   ├── preprocessing.py        # Preprocessing data sebelum inferensi
│   ├── llm_inference.py        # Kode untuk melakukan inferensi LLM
│   └── postprocessing.py       # Postprocessing hasil inferensi
│
├── models/                     # Model LLM dan penyimpanan
│   ├── __init__.py
│   ├── model_loader.py         # Mengelola pemuatan model
│   ├── model_storage.py        # Mengatur akses ke penyimpanan model (misal S3)
│   └── model_config.py         # Konfigurasi model yang digunakan
│
├── vllm/                       # Implementasi VLLM untuk optimisasi
│   ├── __init__.py
│   ├── vllm_batching.py        # Optimasi batching menggunakan VLLM
│   └── vllm_inference.py       # Integrasi VLLM untuk inference
│
├── tests/                      # Unit test dan integration test
│   ├── __init__.py
│   ├── test_api.py             # Test API Gateway
│   ├── test_ray.py             # Test distribusi task ke worker
│   └── test_inference.py       # Test inferensi LLM dan optimisasi VLLM
│
├── requirements.txt            # Dependensi library (Ray, VLLM, FastAPI, dll)
├── Dockerfile                  # Dockerfile untuk deployment
└── README.md                   # Dokumentasi proyek
```
