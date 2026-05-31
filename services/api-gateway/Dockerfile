FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app
COPY pyproject.toml README.md /app/
COPY prototype /app/prototype
COPY services/api-gateway /app/services/api-gateway

RUN pip install --no-cache-dir -e ".[providers]" uvicorn python-multipart prometheus-client sentence-transformers mangum

WORKDIR /app/services/api-gateway
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
