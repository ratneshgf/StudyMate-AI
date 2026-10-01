# StudyMate AI

Enter a topic or photograph a textbook page. Get short notes, exam Q&A and viva Q&A. Django + OpenCV/Tesseract + local Ollama AI.

## Setup
1. Install Tesseract OCR (Windows: UB Mannheim build, then set `TESSERACT_CMD` in `.env`; Ubuntu: `sudo apt install tesseract-ocr`; macOS: `brew install tesseract`).
2. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`, set a real `DJANGO_SECRET_KEY`, install [Ollama](https://ollama.com/download), then run `ollama pull qwen3:4b`. No AI API key is required.
5. `python manage.py migrate && python manage.py runserver`
6. Tests: `python manage.py test`

## Layout
- `accounts/` signup, login, logout, profile (email is the username)
- `study/ai_service.py` prompt, API call, JSON validation
- `study/ocr_service.py` OpenCV preprocessing + Tesseract
- `study/exports.py` PDF and TXT
- `study/views.py` dashboard, result, history, save, regenerate, delete, download, JSON endpoints

## Production deployment

1. Set a long random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, and an explicit comma-separated `ALLOWED_HOSTS` value.
2. Configure PostgreSQL with `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_HOST`.
3. Run Ollama as a local service, select an available `AI_MODEL`, and set `TESSERACT_CMD` if Tesseract is not on `PATH`.
4. Run `python manage.py check --deploy`, `python manage.py migrate`, and `python manage.py collectstatic --noinput`.
5. Run behind HTTPS with `gunicorn studymate.wsgi:application`. Put `/static/` and `/media/` behind persistent storage or a CDN; do not use the Django development server for public traffic.

The `/healthz/` endpoint verifies that the application can reach its database and is suitable for a load balancer health check. Uploaded textbook images are private to their owner and are removed when the associated material is deleted. For local AI, run `ollama pull qwen3:4b` (or configure another installed model in `AI_MODEL`) before generating study material.
