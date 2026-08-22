<div align="center">

# 🧠 MEDRESOLVE AI

### _Clinical Evidence Resolution & Drug–Disease Intelligence Engine_

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_AI-FF6F00?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_DB-7C3AED?style=for-the-badge)](https://www.trychroma.com/)

<br/>

The core AI engine powering the **AuraMed AI** platform.  
Combines **Hybrid RAG**, **Agentic AI**, and **Multi-LLM inference** to deliver  
accurate, evidence-based clinical decision support.

<br/>

---

</div>

<br/>

## ✨ Key Features

| Feature | Description |
|:---|:---|
| 🔍 **Hybrid Retrieval** | Dense semantic search (SentenceTransformers + ChromaDB) + Sparse keyword search (BM25) |
| 🤖 **Agentic AI Workflows** | LangGraph-orchestrated agents that reason through complex clinical queries |
| 🧬 **Multi-LLM Support** | Google Gemini + Groq for high-speed, high-quality generation |
| 📄 **PDF Ingestion Pipeline** | Automated extraction from medical PDFs via PyMuPDF & pdfplumber |
| 🚀 **FastAPI Backend** | High-performance async REST API with auto-generated docs |
| 📊 **Streamlit Dashboard** | Alternative interactive UI for quick exploration |
| 🧪 **RAGAS Evaluation** | Built-in evaluation suite for RAG pipeline quality monitoring |
| 📡 **LangSmith Tracing** | Optional observability & debugging for AI agent workflows |

<br/>

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  MEDRESOLVE AI Engine                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              🚀 FastAPI REST API                 │    │
│  │         /api/query  /api/ingest  /docs           │    │
│  └────────────────────┬────────────────────────────┘    │
│                       │                                 │
│  ┌────────────────────▼────────────────────────────┐    │
│  │           🤖 LangGraph Agent System              │    │
│  │                                                  │    │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │    │
│  │  │ Query    │→ │ Retrieval │→ │ Response     │  │    │
│  │  │ Analysis │  │ Agent     │  │ Generation   │  │    │
│  │  └──────────┘  └─────┬─────┘  └──────────────┘  │    │
│  └──────────────────────┼──────────────────────────┘    │
│                         │                               │
│  ┌──────────────────────▼──────────────────────────┐    │
│  │          📚 Hybrid Retrieval System              │    │
│  │                                                  │    │
│  │  ┌──────────────┐       ┌──────────────────┐    │    │
│  │  │  ChromaDB    │       │     BM25         │    │    │
│  │  │  (Dense /    │  ───  │  (Sparse /       │    │    │
│  │  │   Semantic)  │       │   Keyword)       │    │    │
│  │  └──────────────┘       └──────────────────┘    │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │          📄 Ingestion Pipeline                   │    │
│  │  PDF → Extract → Normalize → Chunk → Index      │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│       ┌──────────┐          ┌──────────┐                │
│       │  Gemini  │          │   Groq   │                │
│       │  (GenAI) │          │  (Fast)  │                │
│       └──────────┘          └──────────┘                │
└─────────────────────────────────────────────────────────┘
```

<br/>

## 📁 Project Structure

```
MEDRESOLVE AI/
│
├── 📂 src/medresolve/              # 🧠 Core Python package
│   ├── agents/                     #    LangGraph AI agents & reasoning logic
│   ├── api/                        #    FastAPI routes & application setup
│   ├── ingestion/                  #    Data parsing, PDF extraction, normalization
│   ├── retrieval/                  #    Hybrid retriever (ChromaDB + BM25)
│   ├── config.py                   #    Application configuration management
│   └── models.py                   #    Pydantic data schemas & types
│
├── 📂 data/                        # 📊 Raw & processed medical datasets
├── 📂 drug_knowledge_base/         # 💊 Drug-specific knowledge files
├── 📂 scripts/                     # 🔧 Utility scripts
│   ├── ingest.py                   #    Data ingestion pipeline runner
│   └── demo.py                     #    Interactive demo script
├── 📂 ui/                          # 📊 Streamlit dashboard components
├── 📂 eval/                        # 🧪 RAG evaluation suite (RAGAS)
│
├── ⚙️ pyproject.toml                # Project metadata & dependencies
├── 📋 requirements.txt             # Pip requirements (alternative)
├── 🔒 .env.example                 # Environment variables template
└── 🚫 .gitignore                   # Git ignore rules
```

<br/>

## 🚀 Getting Started

### 📋 Prerequisites

| Requirement | Details |
|:---|:---|
| 🐍 **Python** | 3.11 or higher |
| 🔑 **Google API Key** | Required — [Get it here](https://aistudio.google.com) |
| 🔑 **Groq API Key** | Optional — [Get it here](https://console.groq.com) |
| 🔑 **LangSmith Key** | Optional — [Get it here](https://smith.langchain.com) |

### 1️⃣ Install Dependencies

```bash
cd "MEDRESOLVE AI"

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install the project
pip install -e .
```

### 2️⃣ Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
# ✅ Required
GOOGLE_API_KEY=your_google_api_key_here

# 📊 Optional: LangSmith observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here
LANGCHAIN_PROJECT=medresolve-ai
```

### 3️⃣ Ingest Data _(Optional)_

```bash
python scripts/ingest.py
```

### 4️⃣ Run the Server

```bash
python -m uvicorn medresolve.api.app:app --reload --host 127.0.0.1 --port 8000
```

```
✅ API running at:     http://127.0.0.1:8000
📖 API Docs (Swagger): http://127.0.0.1:8000/docs
📖 API Docs (ReDoc):   http://127.0.0.1:8000/redoc
```

<br/>

## 🏃‍♂️ Running Options

| Method | Command | Description |
|:---|:---|:---|
| ⚙️ **FastAPI Server** | `uvicorn medresolve.api.app:app --reload` | Main API backend |
| 📊 **Streamlit UI** | `streamlit run ui/app.py` | Alternative dashboard |
| 🎮 **Demo Script** | `python scripts/demo.py` | Quick interactive demo |
| 📥 **Data Ingestion** | `python scripts/ingest.py` | Build vector databases |

<br/>

## 🧪 Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# 🧹 Linting
ruff check src/

# 🎨 Formatting
black src/

# ✅ Type checking
mypy src/

# 🧪 Tests
pytest --cov=medresolve

# 📊 RAG Evaluation
pip install -e ".[eval]"
```

<br/>

## 🛠️ Tech Stack

| Category | Technologies |
|:---|:---|
| 🧠 **Core AI** | LangChain, LangGraph, SentenceTransformers |
| 📚 **Vector DB** | ChromaDB (dense), BM25 (sparse) |
| 🤖 **LLM Providers** | Google Gemini (GenAI), Groq |
| 🚀 **Backend** | FastAPI, Uvicorn, Pydantic v2 |
| 📄 **PDF Processing** | PyMuPDF (fitz), pdfplumber |
| 📊 **UI** | Streamlit |
| 📈 **Evaluation** | RAGAS |
| 🔍 **Observability** | LangSmith, Structlog |
| 🛠️ **Dev Tools** | pytest, black, ruff, mypy |

<br/>

---

<div align="center">

**Part of the [AuraMed AI](../README.md) Platform** 🏥

</div>
