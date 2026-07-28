# Setup and Run

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose (for full stack)
- Redis (for Evolution API)

## Local Dev (Backend Only — No WhatsApp Needed)

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit .env: set DATABASE_URL to sqlite for local dev
python -m app.scripts.seed_demo
uvicorn app.main:app --reload --port 8000
```

## Local Dev (Full Stack with WhatsApp)

```bash
# 1. Start Evolution API (see evolution-api docs for native install)
#    Requires: Node.js 20+, PostgreSQL, Redis
#    Default port: 8080, set AUTHENTICATION_API_KEY in its .env

# 2. Start gateway adapter
cd whatsapp-gateway
npm install
EVOLUTION_API_URL=http://localhost:8080 \
EVOLUTION_API_KEY=your-evo-api-key \
npm start

# 3. Start backend
cd backend
uvicorn app.main:app --reload --port 8000

# 4. Start dashboard
cd dashboard
npm install && npm run dev
```

## Docker (Full Stack)

```bash
cp .env.example .env
# Edit .env: set EVOLUTION_API_KEY
docker compose up --build
```

## Services

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Gateway Adapter | http://localhost:3001 |
| Evolution API | http://localhost:8080 |
| Dashboard | http://localhost:5173 |

## Environment Variables

See [.env.example](../.env.example) for all variables.
