# =============================================================================
# Catalyst — Production Dockerfile (Railway deployment)
# =============================================================================
# Multi-stage build:
#   Stage 1: Build the React frontend with Vite
#   Stage 2: Run Django + Gunicorn with the built frontend as static files
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build React frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Install dependencies first (better Docker layer caching)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy frontend source and build
COPY frontend/ .
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2: Django application
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=catalyst.settings

WORKDIR /app

# Install system dependencies (Tesseract for OCR, Poppler for PDF utils)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy built frontend into Django's static directory
# WhiteNoise will serve these files in production
COPY --from=frontend-build /frontend/dist/ /app/static/frontend/

# Create directories for static files and uploads
RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

# Run collectstatic at startup (needs real env vars), then launch Gunicorn.
# Railway sets PORT env var automatically.
CMD python manage.py collectstatic --noinput && \
    python manage.py migrate --noinput && \
    gunicorn catalyst.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
