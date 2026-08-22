<div align="center">

# 🤖 MedSafety Telegram Bot

### _Your Intelligent Medication Safety Assistant on Telegram_

<br/>

[![Telegram Bot](https://img.shields.io/badge/Telegram-MedSafety_Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/)
[![n8n](https://img.shields.io/badge/n8n-Workflow_Automation-EA4B71?style=for-the-badge&logo=n8n&logoColor=white)](https://n8n.io)
[![Node.js](https://img.shields.io/badge/Node.js-18+-339933?style=for-the-badge&logo=nodedotjs&logoColor=white)](https://nodejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python_API-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

<br/>

**MedSafety Bot** هو بوت تليجرام ذكي مدعوم بالذكاء الاصطناعي يوفر فحص وتأكيد سلامة الأدوية،  
قراءة الروشتات، ومقارنة الأدوية — مع الحفاظ على خصوصيتك الكاملة باستخدام تشفير **AES-256-GCM**.

_An AI-powered Telegram bot for medication verification, prescription reading,_  
_and drug safety checks — with full privacy via **AES-256-GCM** encryption._

<br/>

[🚀 Quick Start](#-quick-start) · [✨ Features](#-features) · [⚙️ Architecture](#%EF%B8%8F-architecture) · [📡 API Reference](#-api-reference) · [🔧 Setup](#-bot-setup)

---

</div>

<br/>

## ✨ Features

### 💊 Core Capabilities

| Command | Description (العربية) | Description (English) |
|:---|:---|:---|
| `/start` | 🏠 القائمة الرئيسية والترحيب | Main menu & welcome |
| `/history` | 📋 سجل الاستعلامات السابقة | Previous query history |
| `/trending` | 🏆 الأدوية الأكثر بحثاً اليوم | Today's most searched drugs |
| `/compare` | ⚖️ مقارنة بين دوائين | Compare two drugs side-by-side |
| `/interactions` | 🔄 فحص التداخلات الدوائية | Check drug-drug interactions |
| `/delete_data` | 🗑️ حذف كافة بياناتي المشفّرة | Delete all my encrypted data |

### 🧠 Intelligence Features

| Feature | Description |
|:---|:---|
| 🔍 **Multi-Source Drug Lookup** | Searches across 5+ databases: Local KB, OpenFDA, RxNorm, RxImage, DailyMed |
| 📸 **Prescription OCR** | Reads and analyzes prescription images automatically |
| ⚠️ **Safety Severity Classification** | Classifies warnings as Critical 🔴, High 🟠, Moderate 🟡, Low 🟢, Info ℹ️ |
| 👤 **Patient Context Awareness** | Personalized warnings based on age, pregnancy, chronic conditions |
| 💊 **Brand ↔ Generic Resolution** | Automatically resolves brand names to generic names and vice versa |
| 🖼️ **Pill Image Identification** | Fetches pill photos from RxImage NLM for visual verification |
| 🔐 **AES-256-GCM Encryption** | All patient data is encrypted end-to-end with zero-knowledge design |

<br/>

## ⚙️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    📱 Telegram User                          │
│              Sends: text, photos, commands                   │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│              🤖 Telegram Bot API                             │
│              @MedSafetyBot                                   │
└──────────────┬───────────────────────────────────────────────┘
               │  Webhook / Polling
               ▼
┌──────────────────────────────────────────────────────────────┐
│           ⚙️  n8n Workflow Engine                             │
│     medication_bot_workflow_deluxe.json                       │
│                                                              │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ Trigger  │→ │ AI Processing│→ │ Response Formatting   │  │
│  │ Handler  │  │ & Routing    │  │ & Safety Enrichment   │  │
│  └──────────┘  └──────┬───────┘  └───────────────────────┘  │
│                       │                                      │
└───────────────────────┼──────────────────────────────────────┘
                        │  HTTP POST /verify
                        ▼
┌──────────────────────────────────────────────────────────────┐
│         📡 MedSafety Verification API                        │
│         (Node.js v4.5 / Python FastAPI v2.0)                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  Drug Resolution Engine                  │ │
│  │                                                         │ │
│  │  1️⃣ Local Knowledge Base (35+ drugs from DailyMed)      │ │
│  │        ↓ not found?                                     │ │
│  │  2️⃣ OpenFDA Official Database (fallback)                │ │
│  │        ↓ enrich with                                    │ │
│  │  3️⃣ RxNorm — Drug ID & Cross-references                │ │
│  │  4️⃣ RxImage NLM — Pill Photos                          │ │
│  │  5️⃣ FAERS — Adverse Event Reports                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │              Patient Safety Engine                      │ │
│  │                                                         │ │
│  │  👶 Pediatric Use     👴 Geriatric Use                   │ │
│  │  🤰 Pregnancy Risk    🩺 Renal / Hepatic                │ │
│  │  ⚖️  Weight Factors    🍼 Lactation                      │ │
│  │  💊 Drug Interactions  ⬛ Black Box Warnings             │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

<br/>

## 📁 File Structure

```
TeleBot/
│
├── 🟢 medication_verify_api.js            # Node.js Multi-Source RAG Server v4.5
│                                           #   → Local KB + OpenFDA + RxNorm + RxImage
│                                           #   → Safety report builder
│                                           #   → Patient context engine
│
├── 🐍 medication_verify_api.py            # Python FastAPI Verification Server v2.0
│                                           #   → Lightweight alternative API
│                                           #   → Sample drug database
│                                           #   → Patient-aware warnings
│
├── 🤖 setup_telegram_bot.py               # Bot Configuration Script
│                                           #   → Sets command menu on Telegram
│                                           #   → Configures bot description
│                                           #   → One-time setup utility
│
└── 📋 medication_bot_workflow_deluxe.json  # n8n Workflow Definition
                                            #   → Complete bot logic flow
                                            #   → Import directly into n8n
                                            #   → Handles all commands & interactions
```

<br/>

## 🚀 Quick Start

### 📋 Prerequisites

| Requirement | Details |
|:---|:---|
| 📱 **Telegram Bot Token** | Create via [@BotFather](https://t.me/BotFather) on Telegram |
| ⚙️ **n8n Instance** | Self-hosted or [n8n.cloud](https://n8n.cloud) |
| 🟢 **Node.js 18+** | For the verification API server |
| 🐍 **Python 3.11+** _(optional)_ | For the alternative Python API |

### 1️⃣ Set Up the Verification API

#### Option A: Node.js Server (Recommended — Multi-Source)

```bash
cd TeleBot
node medication_verify_api.js
```

```
✅ Output:
🚀 MedSafety Multi-Source RAG Server v4.5 on http://localhost:8000
📊 35 drugs loaded | Sources: Local KB + OpenFDA + RxNorm + RxImage + FAERS
```

#### Option B: Python FastAPI Server (Lightweight)

```bash
cd TeleBot
pip install fastapi uvicorn
python medication_verify_api.py
```

### 2️⃣ Import the n8n Workflow

1. Open your **n8n** instance
2. Go to **Settings → Import Workflow**
3. Upload `medication_bot_workflow_deluxe.json`
4. Configure the **Telegram Trigger** node with your Bot Token
5. Point the **HTTP Request** node to your API server URL
6. **Activate** the workflow ✅

### 3️⃣ Configure Bot Commands on Telegram

```bash
python setup_telegram_bot.py
# Enter your Bot Token when prompted
```

```
✅ Output:
🔄 جاري ضبط قائمة أوامر البوت على التلجرام...
✅ تم ضبط الأوامر بنجاح!
🎉 تم إعداد قائمة وتفاصيل البوت على التلجرام بنجاح!
```

<br/>

## 📡 API Reference

### `GET /` — Health Check

```json
{
  "status": "online",
  "service": "MedSafety Multi-Source RAG Server",
  "version": "4.5.0",
  "drugs_loaded": 35,
  "sources": ["Local DailyMed KB", "OpenFDA API", "RxNorm API", "RxImage NLM", "FAERS DB"]
}
```

### `GET /drugs` — List Available Drugs

```json
{
  "count": 35,
  "drugs": ["Amoxicillin", "Aspirin", "Paracetamol", "Ibuprofen", "..."]
}
```

### `POST /verify` — Verify a Medication

**Request:**

```json
{
  "medication_name": "Amoxicillin",
  "patient_context": {
    "age": 70,
    "chronic_conditions": "hypertension, diabetes",
    "is_pregnant": false
  }
}
```

**Response:**

```json
{
  "verification": { "status": "VERIFIED", "source": "multi_source" },
  "image_url": "https://rximage.nlm.nih.gov/...",
  "rxnorm_id": "723",
  "medication": {
    "drug_name": "Amoxicillin",
    "generic_name": "Amoxicillin",
    "category": "Antibiotic (Penicillin)",
    "dosage": "500mg - 1000mg every 8-12 hours...",
    "contraindications": "Penicillin allergy...",
    "interactions": "Warfarin, Allopurinol...",
    "boxed_warning": "No boxed warning"
  },
  "warnings": [
    { "severity": "critical", "section": "Black Box Warning ⬛", "text": "..." },
    { "severity": "high", "section": "Geriatric Use 👴", "text": "..." }
  ],
  "sources": ["DailyMed (NLM/NIH)", "RxImage NLM (Pill Photo)", "RxNorm (NLM)"]
}
```

### Verification Statuses

| Status | Meaning |
|:---|:---|
| ✅ `VERIFIED` | Drug found and fully verified |
| 🟡 `POSSIBLE_MATCH` | Similar drug name found — suggestion provided |
| ❌ `UNVERIFIED` | Drug not found in any database |

### Warning Severity Levels

| Level | Badge | Meaning |
|:---|:---|:---|
| `critical` | 🔴 | Life-threatening — immediate action required |
| `high` | 🟠 | Serious risk — medical consultation needed |
| `moderate` | 🟡 | Notable concern — monitor closely |
| `low` | 🟢 | Minor consideration |
| `info` | ℹ️ | General information |

<br/>

## 🔐 Security & Privacy

| Feature | Implementation |
|:---|:---|
| 🔒 **Encryption** | AES-256-GCM for all stored patient data |
| 🚫 **Zero-Knowledge** | Server cannot read patient data at rest |
| 🗑️ **Right to Delete** | `/delete_data` command wipes all user data |
| 🛡️ **No Data Sharing** | Patient context is processed in-memory only |

<br/>

## 🌍 Data Sources

| Source | Type | Coverage |
|:---|:---|:---|
| 📂 **Local DailyMed KB** | Curated JSON files | 35+ common drugs with full monographs |
| 🏛️ **OpenFDA API** | Live REST API | 100,000+ FDA-approved drug labels |
| 💊 **RxNorm (NLM)** | Live REST API | Drug name normalization & cross-refs |
| 🖼️ **RxImage (NLM)** | Live REST API | Pill identification photos |
| 📊 **FAERS** | Adverse event data | Post-market safety reports |

<br/>

---

<div align="center">

### 💬 Start chatting with MedSafety Bot now!

<br/>

🏥 _Safer medications, smarter decisions — right from Telegram_ 📱

<br/>

**Part of the [AuraMed AI](../README.md) Platform**

</div>
