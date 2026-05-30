FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY prototype /app/prototype
COPY services/semantic-compiler /app/services/semantic-compiler

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings python-multipart prometheus-client httpx

WORKDIR /app/services/semantic-compiler
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
