FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY prototype /app/prototype
COPY services/training-pipeline /app/services/training-pipeline

RUN pip install --no-cache-dir -e ".[providers]" uvicorn python-multipart prometheus-client

WORKDIR /app/services/training-pipeline
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
