# NarrAI API: FastAPI + pandas analytics + LLM narration.
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user. Data lives in the database (DATABASE_URL), never in the image.
RUN useradd --create-home --uid 10001 narrai
USER narrai

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/api/health', timeout=4)"

# Migrates the database (and seeds demo data if NARRAI_SEED_DEMO=1) before starting.
CMD ["./docker-entrypoint.sh"]
