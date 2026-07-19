# API

FastAPI backend for the meeting AI Agent MVP.

## Run with Docker

From the repository root:

```bash
cp .env.example .env
docker-compose up --build
```

Swagger UI: http://localhost:8000/docs

## Run locally without Docker

Start PostgreSQL separately, then:

```bash
cd api
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg://meeting_agent:meeting_agent@localhost:5432/meeting_agent
set STORAGE_DIR=../storage
set OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload
```
