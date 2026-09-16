# 🔨 RAGforge

**RAGforge** is a production-ready template for building Retrieval-Augmented Generation (RAG) applications using:

- 🐍 **Python**
- 🔗 **LangChain**
- 🔴 **Qdrant** (for vector storage)
- 🐘 **PostgreSQL** (for metadata and structured data)

This project provides a modular, extensible foundation for quickly prototyping or deploying RAG pipelines. Designed for developers, researchers, and teams building LLM-powered apps that require fast, context-aware information retrieval.

---

## 🚀 Features

- ✅ Plug-and-play RAG pipeline with LangChain
- 🔍 Qdrant integration for fast vector search
- 🗃 PostgreSQL support for hybrid structured-unstructured queries
- 🧱 Clean project structure & dependency injection
- 🔧 Docker-ready setup for easy deployment

---

## 📦 Use Cases

- Internal knowledge bases  
- Chatbots with document grounding  
- Semantic search engines  
- R&D assistants  

---

## 📁 Project Structure
```

```

## Quick Start

```sh
# Copy environment file
cp .env.example .env

# Install dependencies
uv sync

# Start Services
docker-compose up -d

# Run Migrations
alembic upgrade head

# Run The Application
uvicorn app.main:app

# Run The Frontend
cd /web && npm install && npm run dev
```

## Access the Application
* **API**: http://localhost:8000  
* **API Docs**: http://localhost:8000/docs  
* **Qdrant**: http://localhost:6333  
* **PostgreSQL**: http://localhost:5432  

## 📄 License

MIT — feel free to use, extend, and contribute!
