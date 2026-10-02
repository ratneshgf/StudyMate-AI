FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only-static-key DJANGO_DEBUG=0 python manage.py collectstatic --noinput
RUN useradd --create-home appuser && mkdir -p /app/media && chown -R appuser:appuser /app/media
USER appuser
CMD ["sh", "-c", "python manage.py setup_database && exec gunicorn studymate.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 300 --access-logfile -"]
