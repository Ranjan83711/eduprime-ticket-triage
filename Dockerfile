# One image for every host (Hugging Face Spaces, Azure, Render): FastAPI serves the API and the React build.

# ---- 1. Build the React frontend ----
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    DB_PATH=/tmp/triage.db \
    CACHE_DIR=/tmp/triage-cache

WORKDIR /app/backend
COPY backend/requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend/dist

# Hugging Face Spaces runs containers as a non-root user (uid 1000).
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
