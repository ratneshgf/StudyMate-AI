# StudyMate AI

Enter a topic or photograph a textbook page. Get short notes, exam Q&A and viva Q&A. Django + OpenCV/Tesseract + local Ollama AI.

## Setup
1. Install Tesseract OCR (Windows: UB Mannheim build, then set `TESSERACT_CMD` in `.env`; Ubuntu: `sudo apt install tesseract-ocr`; macOS: `brew install tesseract`).
2. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`, set a real `DJANGO_SECRET_KEY`, install [Ollama](https://ollama.com/download), then run `ollama pull qwen3:4b`. No AI API key is required.
5. `python manage.py migrate && python manage.py runserver`
6. Tests: `python manage.py test --settings=studymate.test_settings`

## Layout
- `accounts/` signup, login, logout, profile (email is the username)
- `study/ai_service.py` prompt, API call, JSON validation
- `study/ocr_service.py` OpenCV preprocessing + Tesseract
- `study/exports.py` PDF and TXT
- `study/views.py` dashboard, result, history, save, regenerate, delete, download, JSON endpoints

## Production deployment

For the Render backend and Vercel frontend, follow [the deployment guide](docs/deployment.md). Render uses Gemini and Supabase; local development can keep using Ollama. The `/healthz/` endpoint checks the database.

## Supabase PostgreSQL

See [the database setup and data migration guide](docs/supabase.md). Existing Django migrations create users, profiles, study material, exam questions, viva questions, and session tables. No Supabase API key is needed for this server-side connection.

## Local generation performance

Ollama generation uses five normal requests: notes, related concepts, exam, viva and MCQ.
Each question request includes all three difficulty levels. Structured output fixes field/count
errors; at most one targeted repair per section requests only missing levels and an alternate candidate.
The Study page streams completed sections immediately. A complete result is saved to history;
errors or disconnects discard incomplete records. Repeat text searches reuse only the same user's
validated current-format material. New set and New test still generate fresh questions.

Ollama keeps the model warm for 15 minutes. OLLAMA_NUM_BATCH defaults to 128 and OLLAMA_NUM_GPU
defaults to -1 (automatic). The local GTX 1650 / qwen3:4b setup was tested with OLLAMA_NUM_GPU=99
to fit the whole model on its 4 GB GPU; this is a machine-specific .env setting, not a portable default.
Streaming deployments must disable reverse-proxy response buffering for the Study POST endpoint.
