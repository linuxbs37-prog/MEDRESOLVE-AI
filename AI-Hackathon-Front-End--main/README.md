<div align="center">

# 🖥️ AuraMed AI — Web Frontend

### _Modern Healthcare Assistant Interface_

<br/>

[![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/HTML)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/CSS)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6+-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![Supabase](https://img.shields.io/badge/Supabase-Auth_&_DB-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Vercel](https://img.shields.io/badge/Vercel-Deploy-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com)

<br/>

A sleek, responsive web interface for the **AuraMed AI** platform — providing  
AI-powered medical consultations, drug verification, and clinical report generation.

<br/>

---

</div>

<br/>

## ✨ Features

| Feature | Description |
|:---|:---|
| 🤖 **AI Chat Assistant** | Interactive conversation with the MedResolve AI engine for clinical queries |
| 📝 **Patient Data Form** | Comprehensive form for patient demographics, conditions & medication history |
| 📊 **Medical Reports** | Auto-generated clinical reports with drug analysis and safety insights |
| 🔐 **Authentication** | Secure login & signup powered by Supabase Auth |
| 🌍 **i18n (AR/EN)** | Full internationalization — switch between Arabic and English seamlessly |
| 📱 **Responsive Design** | Beautiful UI that works on desktop, tablet, and mobile |
| 💊 **Drug Lookup** | Instant medication search with safety info and interaction warnings |

<br/>

## 📁 File Structure

```
AI-Hackathon-Front-End--main/
│
├── 🏠 index.html                # Landing page
├── 🤖 assistant.html            # AI Chat assistant interface
├── 📝 patient-form.html         # Patient data entry form
├── 📊 report.html               # Medical report viewer & generator
├── 🔐 login.html                # User login page
├── 📋 signup.html               # User registration page
│
├── 📂 js/                       # JavaScript modules
│   ├── assistant.js             #   Chat logic & AI communication
│   ├── api-client.js            #   Backend API client (FastAPI)
│   ├── auth.js                  #   Supabase authentication handler
│   ├── i18n.js                  #   Internationalization (Arabic/English)
│   ├── medicines.js             #   Drug lookup & display
│   ├── patient.js               #   Patient form validation & submission
│   ├── report.js                #   Report generation & rendering
│   └── supabase-client.js       #   Supabase client initialization
│
├── 📂 css/
│   └── styles.css               #   Global styling
│
├── ⚙️ vercel.json                # Vercel deployment configuration
├── 📖 SUPABASE_SETUP_GUIDE.md   # Supabase setup instructions
└── 📖 VERCEL_DEPLOYMENT_GUIDE.md # Vercel deployment guide
```

<br/>

## 🚀 Quick Start

### 🔧 Local Development

```bash
# Navigate to the frontend directory
cd AI-Hackathon-Front-End--main

# Start a local HTTP server
python -m http.server 5500 --bind 127.0.0.1

# Open in browser
# 🌐 http://127.0.0.1:5500
```

> ⚠️ Make sure the **MEDRESOLVE AI Backend** is running on `http://127.0.0.1:8000` for full functionality.

### ☁️ Vercel Deployment

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel deploy
```

> 📖 See [VERCEL_DEPLOYMENT_GUIDE.md](VERCEL_DEPLOYMENT_GUIDE.md) for detailed instructions.

<br/>

## 🔗 Pages & Routes

| Page | URL | Description |
|:---|:---|:---|
| 🏠 Landing | `/index.html` | Welcome page with platform overview |
| 🤖 Assistant | `/assistant.html` | AI chat interface — main interaction point |
| 📝 Patient Form | `/patient-form.html` | Enter patient details for personalized analysis |
| 📊 Report | `/report.html` | View generated clinical reports |
| 🔐 Login | `/login.html` | User authentication |
| 📋 Sign Up | `/signup.html` | New user registration |

<br/>

## 🌍 Internationalization

The platform supports full **Arabic (RTL)** and **English (LTR)** localization:

| Language | Direction | Coverage |
|:---|:---|:---|
| 🇪🇬 العربية | RTL ← | Full UI + medical terms |
| 🇬🇧 English | LTR → | Full UI + medical terms |

Language switching is handled by `js/i18n.js` with comprehensive translation dictionaries.

<br/>

## 🔐 Authentication (Supabase)

| Feature | Implementation |
|:---|:---|
| 📧 Email/Password | Standard Supabase Auth |
| 🔄 Session Management | Automatic token refresh |
| 🛡️ Protected Routes | Auth-guarded pages |
| 🗂️ User Data | Stored securely in Supabase |

> 📖 See [SUPABASE_SETUP_GUIDE.md](SUPABASE_SETUP_GUIDE.md) for configuration.

<br/>

---

<div align="center">

**Part of the [AuraMed AI](../README.md) Platform** 🏥

</div>
