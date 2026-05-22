# FastAPI Service

The FastAPI service lives under `backend/`.
It reads environment variables from process env, `.env`, `.env.local`, and `../.env.local`, so the repo-root `.env.local` can be reused during local development.

It is intended for work that should not run in browser or lightweight Next.js route handlers:

- notice collection
- document analysis
- Gemini AI/OCR calls
- Gemini pivot translation with validation
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

Translate a notice with the Gemini validation pipeline:

```bash
curl -X POST http://127.0.0.1:8000/notices/{notice_id}/translate \
  -H "Content-Type: application/json" \
  -d '{"target_language":"vi"}'
```

The pipeline uses `GEMINI_API_KEY` or `GEMINI_API_KEYS`, stores the full result in `notice_ai_translations`, updates `notices.summary_translations`, and rebuilds `notice_cards` when validation passes.
For crawled notices, the service fetches `notices.detail_url` and fills `notices.original_text` before translation if the crawler candidate does not already have body text.
