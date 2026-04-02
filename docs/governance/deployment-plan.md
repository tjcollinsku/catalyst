# Catalyst — Deployment Plan (IBM Cloud)

**Last Updated:** 2026-04-01
**Purpose:** Plan for deploying Catalyst to IBM Cloud so it's accessible via URL.

---

## Target Architecture

```
┌────────────────────────────────────┐
│          IBM Cloud                  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │   Container (Docker)          │  │
│  │                              │  │
│  │   Django Backend              │  │
│  │   + Static Files (whitenoise)│  │
│  │   + Gunicorn WSGI            │  │
│  │   Port 8000                  │  │
│  └──────────┬───────────────────┘  │
│             │                      │
│  ┌──────────▼───────────────────┐  │
│  │   IBM Cloud Databases        │  │
│  │   PostgreSQL                 │  │
│  │   (Managed service)          │  │
│  └──────────────────────────────┘  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │   Frontend (React build)     │  │
│  │   Served as static files     │  │
│  │   by Django/whitenoise       │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
```

---

## Deployment Components

### 1. Dockerfile

```
FROM python:3.11-slim

# Install system dependencies (Tesseract for OCR)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn whitenoise

# Copy backend code
COPY backend/ .

# Copy pre-built frontend static files
COPY frontend/dist/ /app/static/frontend/

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "catalyst.wsgi:application", "--bind", "0.0.0.0:8000"]
```

This is a starting point — will need refinement during Milestone 4.

### 2. Frontend Build

Build the React app locally, then include the built files in the Docker image:

```bash
cd frontend
npm run build    # Produces dist/ directory
```

The built files get served by Django using whitenoise middleware.

### 3. Database

Use IBM Cloud Databases for PostgreSQL (managed service). This gives:
- Automatic backups
- TLS encryption in transit
- Connection string via environment variable

### 4. Environment Variables

| Variable | Purpose | Where |
|----------|---------|-------|
| `DATABASE_URL` | PostgreSQL connection string | IBM Cloud service binding |
| `DJANGO_SECRET_KEY` | Django secret key | IBM Cloud env var |
| `DJANGO_DEBUG` | Debug mode (False in production) | IBM Cloud env var |
| `ALLOWED_HOSTS` | Hostname for the deployed app | IBM Cloud env var |
| `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | AI memo generation | IBM Cloud env var |

### 5. Static Files

Use `whitenoise` to serve static files directly from Django in production. This avoids needing a separate nginx or CDN for V1.

```python
# settings.py (production)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ... rest of middleware
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

---

## IBM Cloud Service Options

Research these during Milestone 4 prep:

| Service | Purpose | Tier |
|---------|---------|------|
| IBM Cloud Code Engine | Serverless container runtime | Pay-as-you-go |
| IBM Cloud Kubernetes Service (IKS) | Full Kubernetes | Pay-as-you-go (overkill for V1) |
| IBM Cloud Databases for PostgreSQL | Managed PostgreSQL | Pay-as-you-go |
| IBM Cloud Container Registry | Docker image storage | Free tier available |

**Recommended for V1:** Code Engine (simplest container deployment) + Databases for PostgreSQL.

**Fallback options** if IBM Cloud proves difficult:
- Railway (one-click Django deployment)
- Render (free tier for small apps)
- DigitalOcean App Platform

---

## Pre-Deployment Checklist

- [ ] Dockerfile builds successfully
- [ ] Frontend builds (`npm run build` succeeds)
- [ ] Django runs with `DEBUG=False` and serves static files via whitenoise
- [ ] Database migrations run against IBM Cloud PostgreSQL
- [ ] Environment variables are set in IBM Cloud
- [ ] ALLOWED_HOSTS includes the IBM Cloud hostname
- [ ] CSRF_TRUSTED_ORIGINS includes the IBM Cloud hostname
- [ ] App is accessible via browser at the IBM Cloud URL
- [ ] Upload a test PDF and verify the full pipeline works
- [ ] Demo the Golden Path end-to-end on the deployed instance

---

## What We Are NOT Doing for V1

- No CI/CD pipeline (manual deployment is fine for V1)
- No custom domain (IBM Cloud default URL is fine)
- No CDN for static files (whitenoise is sufficient)
- No auto-scaling (single container is fine)
- No Kubernetes (Code Engine is simpler)
