# syntax=docker/dockerfile:1

# --- Stage 1: build the production frontend ---
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: runtime (backend + bundled UI) ---
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock README.md ./
COPY backend/ ./backend/
# Serve the built SPA from backend/static (main.py._frontend_dir looks here).
COPY --from=frontend /app/frontend/dist ./backend/static
RUN uv sync --frozen --no-dev

EXPOSE 8001
ENV MODEL_SENATE_HOST=0.0.0.0 MODEL_SENATE_PORT=8001
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
