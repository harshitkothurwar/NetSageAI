# NetSage AI

Cisco troubleshooting assistant: deterministic Python checks + LLM diagnosis + human review dashboard.

## Layout

- `backend/` — FastAPI (`main.py`), `rule_checker.py`, `ai_service.py`
- `frontend/` — Vite + React + Tailwind (`src/App.jsx`)

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# set OPENAI_API_KEY or ANTHROPIC_API_KEY and LLM_PROVIDER
uvicorn main:app --reload --port 8000
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000.

## API

- `POST /api/diagnose` `{ "symptom", "show_output" }`
- `POST /api/review` `{ "case_id", "status": "Accept"|"Edit"|"Reject", "edited_fix" }`
- `GET /api/stats`
