<div align="center">

# 🏥 AuraMed AI

### _Clinical Evidence Resolution & Drug–Disease Intelligence Platform_

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-0.3+-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)](https://langchain.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_AI-FF6F00?style=for-the-badge&logo=data:image/svg+xml;base64,&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

<br/>

**AuraMed AI** is an advanced AI-powered medical assistant platform that combines  
**Retrieval-Augmented Generation (RAG)**, **Agentic AI Workflows**, and **Multi-Source Drug Intelligence**  
to deliver safe, accurate, and evidence-based clinical decision support.

<br/>

[🚀 Quick Start](#-quick-start) · [✨ Features](#-key-features) · [🏗️ Architecture](#%EF%B8%8F-system-architecture) · [📱 Telegram Bot](#-telegram-bot--medsafety) · [🤝 Contributing](#-contributing)

---

</div>

<br/>

## ✨ Key Features

| Feature | Description |
|:---|:---|
| 🧠 **Hybrid RAG Engine** | Combines dense semantic search (SentenceTransformers + ChromaDB) with sparse keyword retrieval (BM25) for maximum accuracy |
| 🤖 **Agentic AI Workflows** | LangGraph-powered intelligent agents that reason through complex clinical queries step-by-step |
| 🔬 **Multi-LLM Inference** | Seamlessly integrates Google Gemini & Groq for high-speed, high-quality natural language generation |
| 📄 **Smart PDF Ingestion** | Automated pipeline using PyMuPDF & pdfplumber to extract, normalize, and index medical literature |
| 💊 **Drug Safety Intelligence** | Multi-source verification via Local KB, OpenFDA, RxNorm, RxImage (NLM), and DailyMed |
| 🛡️ **Patient Safety Guardrails** | Context-aware warnings based on age, pregnancy, chronic conditions, and drug interactions |
| 🔐 **Privacy-First Design** | AES-256-GCM encryption for all patient data with zero-knowledge architecture |
| 🌍 **Multilingual Support** | Full Arabic & English i18n support across the entire platform |
| 📱 **Telegram Bot** | MedSafety Bot with n8n workflow automation for prescription verification on-the-go |
| 📊 **RAG Evaluation** | Built-in RAGAS evaluation suite for continuous quality monitoring |

<br/>

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        🏥 AuraMed AI Platform                       │
├─────────────────┬──────────────────────┬────────────────────────────┤
│                 │                      │                            │
│   🖥️ Frontend    │   ⚙️ Backend          │   📱 Telegram Bot           │
│   (Web UI)      │   (MEDRESOLVE AI)    │   (MedSafety Bot)          │
│                 │                      │                            │
│  ┌───────────┐  │  ┌────────────────┐  │  ┌──────────────────────┐  │
│  │ HTML/CSS  │  │  │   FastAPI      │  │  │  n8n Workflow Engine  │  │
│  │ JS + i18n │  │  │   REST API     │  │  │  + Verification API  │  │
│  │ Supabase  │  │  │                │  │  │                      │  │
│  └─────┬─────┘  │  ├────────────────┤  │  ├──────────────────────┤  │
│        │        │  │  🧠 AI Agents   │  │  │  Multi-Source RAG    │  │
│        │        │  │  (LangGraph)   │  │  │  ┌────────────────┐  │  │
│        │        │  │                │  │  │  │ Local KB       │  │  │
│        ├────────┤  ├────────────────┤  │  │  │ OpenFDA API    │  │  │
│        │  API   │  │  📚 Hybrid RAG  │  │  │  │ RxNorm API     │  │  │
│        │ Calls  │  │  ChromaDB      │  │  │  │ RxImage NLM    │  │  │
│        │◄──────►│  │  + BM25        │  │  │  │ DailyMed       │  │  │
│        │        │  │                │  │  │  └────────────────┘  │  │
│        │        │  ├────────────────┤  │  └──────────────────────┘  │
│        │        │  │  📄 Ingestion   │  │                            │
│        │        │  │  Pipeline      │  │                            │
│        │        │  └────────────────┘  │                            │
└─────────────────┴──────────────────────┴────────────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
        ┌─────▼─────┐ ┌────▼────┐  ┌──────▼──────┐
        │  Gemini   │ │  Groq   │  │ LangSmith   │
        │  (GenAI)  │ │  (LLM)  │  │ (Tracing)   │
        └───────────┘ └─────────┘  └─────────────┘
```

<br/>

## 📁 Project Structure

```
AuraMed-AI/
│
├── 📂 MEDRESOLVE AI/               # 🧠 Core AI Backend
│   ├── src/medresolve/
│   │   ├── agents/                  #    LangGraph AI agents & reasoning
│   │   ├── api/                     #    FastAPI routes & app setup
│   │   ├── ingestion/               #    PDF extraction & normalization
│   │   ├── retrieval/               #    Hybrid retriever (ChromaDB + BM25)
│   │   ├── config.py                #    Configuration management
│   │   └── models.py                #    Pydantic schemas & data types
│   ├── data/                        #    Medical datasets
│   ├── drug_knowledge_base/         #    Drug knowledge files
│   ├── scripts/                     #    Utility scripts (ingest, demo)
│   ├── ui/                          #    Streamlit dashboard
│   ├── eval/                        #    RAG evaluation suite
│   ├── pyproject.toml               #    Dependencies & project config
│   └── requirements.txt             #    Pip requirements
│
├── 📂 AI-Hackathon-Front-End--main/ # 🖥️ Web Frontend
│   ├── index.html                   #    Landing page
│   ├── assistant.html               #    AI Chat assistant
│   ├── patient-form.html            #    Patient data form
│   ├── report.html                  #    Medical report viewer
│   ├── login.html / signup.html     #    Auth pages (Supabase)
│   ├── js/                          #    JavaScript modules
│   │   ├── assistant.js             #      Chat logic
│   │   ├── api-client.js            #      Backend API client
│   │   ├── auth.js                  #      Authentication
│   │   ├── i18n.js                  #      Internationalization (AR/EN)
│   │   ├── medicines.js             #      Drug lookup
│   │   ├── patient.js               #      Patient form handler
│   │   ├── report.js                #      Report generation
│   │   └── supabase-client.js       #      Supabase client
│   ├── css/styles.css               #    Styling
│   └── vercel.json                  #    Vercel deployment config
│
├── 📂 TeleBot/                      # 📱 Telegram Bot
│   ├── medication_verify_api.js     #    Multi-source RAG server (Node.js)
│   ├── medication_verify_api.py     #    Verification API (Python/FastAPI)
│   ├── setup_telegram_bot.py        #    Bot commands & UI setup
│   └── medication_bot_workflow_deluxe.json  # n8n workflow definition
│
├── start.bat                        # 🚀 One-click launcher (Windows)
└── README.md                        # 📖 You are here!
```

<br/>

## 🛠️ Technology Stack

<div align="center">

### Core AI & RAG
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=flat-square&logo=langchain&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-FF6F00?style=flat-square&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_DB-purple?style=flat-square)
![BM25](https://img.shields.io/badge/BM25-Sparse_Retrieval-blue?style=flat-square)
![SentenceTransformers](https://img.shields.io/badge/SentenceTransformers-Embeddings-orange?style=flat-square)

### LLM Providers
![Google Gemini](https://img.shields.io/badge/Google_Gemini-4285F4?style=flat-square&logo=google&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Fast_Inference-black?style=flat-square)

### Backend & API
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-green?style=flat-square)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat-square&logo=pydantic&logoColor=white)

### Frontend & UI
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat-square&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat-square&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?style=flat-square&logo=supabase&logoColor=white)

### Bot & Automation
![Telegram](https://img.shields.io/badge/Telegram_Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-Workflow_Automation-EA4B71?style=flat-square&logo=n8n&logoColor=white)
![Node.js](https://img.shields.io/badge/Node.js-339933?style=flat-square&logo=nodedotjs&logoColor=white)

### Data & External APIs
![OpenFDA](https://img.shields.io/badge/OpenFDA-Official_API-003DA5?style=flat-square)
![RxNorm](https://img.shields.io/badge/RxNorm-NLM/NIH-red?style=flat-square)
![DailyMed](https://img.shields.io/badge/DailyMed-Drug_Labels-green?style=flat-square)

</div>

<br/>

## 🚀 Quick Start

### 📋 Prerequisites

| Requirement | Version |
|:---|:---|
| 🐍 Python | 3.11 or higher |
| 🔑 Google API Key | [Get it here](https://aistudio.google.com) |
| 🔑 Groq API Key _(optional)_ | [Get it here](https://console.groq.com) |

### ⚡ Option 1: One-Click Launch (Windows)

```bash
# Just double-click or run:
start.bat
```

> This automatically starts the **FastAPI Backend** on `http://127.0.0.1:8000` and the **Web Frontend** on `http://127.0.0.1:5500`, then opens your browser! 🎉

### 🔧 Option 2: Manual Setup

#### 1️⃣ Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/AuraMed-AI.git
cd AuraMed-AI
```

#### 2️⃣ Set Up the Backend

```bash
cd "MEDRESOLVE AI"

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -e .
```

#### 3️⃣ Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and add your API keys:
#   GOOGLE_API_KEY=your_key_here
#   GROQ_API_KEY=your_key_here (optional)
```

#### 4️⃣ Ingest Medical Data _(Optional)_

```bash
python scripts/ingest.py
```

#### 5️⃣ Start the Backend

```bash
python -m uvicorn medresolve.api.app:app --reload --host 127.0.0.1 --port 8000
```

#### 6️⃣ Start the Frontend

```bash
cd "../AI-Hackathon-Front-End--main"
python -m http.server 5500 --bind 127.0.0.1
```

#### 7️⃣ Open in Browser

```
🖥️  Frontend:  http://127.0.0.1:5500/assistant.html
📡  API Docs:  http://127.0.0.1:8000/docs
```

<br/>

## 📱 Telegram Bot — MedSafety

The **MedSafety Bot** brings drug verification and safety checks directly to Telegram with intelligent n8n workflow automation.

| Feature | Description |
|:---|:---|
| 💊 Drug Verification | Verify medications from 5+ sources in real-time |
| 📸 Prescription OCR | Read and analyze prescription images |
| ⚖️ Drug Comparison | Compare two drugs side-by-side |
| 🔄 Interaction Checker | Detect dangerous drug-drug interactions |
| 🏆 Trending Drugs | See what's being searched today |
| 🗑️ Data Privacy | Delete all your encrypted data anytime |

> 📖 **[Full Telegram Bot Documentation →](TeleBot/README.md)**

<br/>

## 🏃‍♂️ Running Options

| Method | Command | Description |
|:---|:---|:---|
| 🚀 **One-Click** | `start.bat` | Launches everything automatically |
| ⚙️ **Backend Only** | `uvicorn medresolve.api.app:app --reload` | FastAPI server on port 8000 |
| 📊 **Streamlit UI** | `streamlit run ui/app.py` | Alternative dashboard |
| 🎮 **Demo Mode** | `python scripts/demo.py` | Quick interactive demo |

<br/>

## 🧪 Development & Evaluation

```bash
# Install dev dependencies (formatting, linting, testing)
pip install -e ".[dev]"

# Run tests
pytest --cov=medresolve

# Run linting
ruff check src/
black --check src/

# Run RAG evaluation suite
pip install -e ".[eval]"
```

<br/>

## 🌐 Deployment

### Vercel (Frontend)

The frontend is pre-configured for **Vercel** deployment:

```bash
cd AI-Hackathon-Front-End--main
vercel deploy
```

> 📖 See [VERCEL_DEPLOYMENT_GUIDE.md](AI-Hackathon-Front-End--main/VERCEL_DEPLOYMENT_GUIDE.md) for detailed instructions.

### Supabase (Auth & Database)

> 📖 See [SUPABASE_SETUP_GUIDE.md](AI-Hackathon-Front-End--main/SUPABASE_SETUP_GUIDE.md) for setup instructions.

<br/>

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. 🍴 **Fork** the repository
2. 🌿 **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. 💾 **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. 📤 **Push** to the branch (`git push origin feature/amazing-feature`)
5. 🔀 **Open** a Pull Request

<br/>

## 📜 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

<br/>

---

<div align="center">

### 🌟 Star this repo if you find it useful!

<br/>

Made with ❤️ by the **AuraMed AI Team**

🧬 _Empowering safer healthcare decisions through AI_ 🧬

<br/>

[![GitHub Stars](https://img.shields.io/github/stars/YOUR_USERNAME/AuraMed-AI?style=social)](https://github.com/YOUR_USERNAME/AuraMed-AI)

</div>
