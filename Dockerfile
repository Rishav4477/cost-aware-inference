FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY inference ./inference
COPY scripts ./scripts
COPY config ./config
COPY web ./web
RUN useradd --uid 10001 --create-home inference && chown -R inference:inference /app
USER 10001
EXPOSE 8000 10000
CMD ["sh", "-c", "uvicorn inference.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
