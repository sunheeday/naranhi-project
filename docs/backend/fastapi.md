# FastAPI Service

The FastAPI service lives under `backend/`.

It is intended for work that should not run in browser or lightweight Next.js route handlers:

- notice collection
- document analysis
- AI/OCR calls
- translation
- NEIS API integration
- Google Calendar integration
- longer-running server workflow orchestration

Run locally:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Create a notice:

```bash
curl -X POST http://127.0.0.1:8000/notices \
  -H "Content-Type: application/json" \
  -d '{"title":"현장체험학습 안내","raw_text":"준비물과 제출 기한 안내"}'
```

The create endpoint writes to Supabase when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured.
