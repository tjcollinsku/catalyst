# Dockerfile for Catalyst Django Backend
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies (includes Tesseract for OCR and Poppler for PDF utils)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY . /app

# Collect static files (if using Django staticfiles)
RUN mkdir -p /app/static

# Expose port
EXPOSE 8000

# Set environment variables for Django
ENV DJANGO_SETTINGS_MODULE=catalyst.settings

# Start server with Gunicorn for production
CMD ["gunicorn", "catalyst.wsgi:application", "--bind", "0.0.0.0:8000"]
