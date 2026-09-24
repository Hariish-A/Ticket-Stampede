FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql .
COPY app ./app

# Integration tests: `docker compose run --rm seller-tests` (built only on demand).
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]

FROM base AS runtime
EXPOSE 8000
HEALTHCHECK --interval=2s --timeout=2s --retries=30 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=1).status == 200 else 1)"

# One worker per container: scaling is done with more containers (Plan.md D11).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--loop", "uvloop", "--http", "httptools", "--no-access-log", "--backlog", "4096"]
