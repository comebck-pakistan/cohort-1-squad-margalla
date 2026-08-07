# WhatsApp Commerce Copilot 🚀

A complete AI-powered WhatsApp commerce platform with a modern React dashboard, Python/FastAPI backend, and the Evolution API for seamless WhatsApp integration.

## Features
- **AI Auto-replies**: Automatically responds to customers browsing your catalog.
- **Human Mode**: One-click toggle to disable AI and chat manually with customers.
- **Stock Management**: Track and edit product stock directly from the dashboard.
- **Live Syncing**: Everything happens in real-time.

---

## 🛠️ Zero-Setup Quickstart Guide

This project is fully dockerized for the backend and database. To run it on a fresh PC, follow these simple steps:

### Prerequisites
1. Install **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (Make sure it is running).
2. Install **[Node.js](https://nodejs.org/en)** (Version 18+).
3. Have **Git** installed to clone the repo.

### Step 1: Start the Backend Services
Open a terminal in the root folder of this project and run:
```bash
docker compose up -d --build
```
*This will automatically download and start the Database, Redis, Evolution API gateway, and the Python Backend.*

### Step 2: Start the Dashboard
Open a **new** terminal window, navigate into the `dashboard` folder, and start the React app:
```bash
cd dashboard
npm install
npm run dev
```

### Step 3: Open the App
Go to your browser and open:
👉 **[http://localhost:5173/](http://localhost:5173/)**

You're done! The dashboard will load and the backend services are all connected. 

---

## 📱 Connecting WhatsApp
1. In the Dashboard, click on **Conversations**.
2. Click **Connect WhatsApp** in the sidebar.
3. Scan the QR code with your WhatsApp app (Linked Devices).
4. You are now live! Any messages sent to that WhatsApp number will appear in the dashboard.

## ⚙️ Advanced: Using LangChain with Gemini (Optional)

The backend keeps working with its deterministic catalogue pipeline when no AI
key is present. To enable LangChain for customer queries, edit the root `.env`
file and add:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Every inbound demo or WhatsApp message then passes through the LangChain intent
chain. LangChain response generation is used for ambiguous or low-confidence
queries and receives only store-scoped products and policies retrieved by the
backend.

Then restart the backend: `docker compose restart backend`.
