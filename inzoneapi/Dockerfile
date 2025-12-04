# ============================================================================
# InZone API - Production Docker Image
# ============================================================================
# Multi-stage build for optimized production deployment
# ============================================================================

FROM python:3.12-slim as base

# Metadata labels
LABEL maintainer="InZone Team"
LABEL description="InZone Social Media API Backend"
LABEL version="1.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_HOME=/app

# ============================================================================
# Dependencies Stage - Install system packages
# ============================================================================
FROM base as dependencies

# Install system dependencies for OpenCV, FFmpeg, and media processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV dependencies
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libgthread-2.0-0 \
    libstdc++6 \
    libgl1-mesa-dev \
    # Media processing
    ffmpeg \
    libfontconfig1 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ============================================================================
# Application Stage - Copy application code and install Python dependencies
# ============================================================================
FROM dependencies as application

# Set working directory
WORKDIR $APP_HOME

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code with proper structure
# Core application files
COPY app.py config.py dependencies.py ./

# Copy Firebase credentials
COPY key.json ./

# Copy application directories
COPY services/ ./services/
COPY routes/ ./routes/
COPY config/ ./config/
COPY utils/ ./utils/
COPY models/ ./models/

# Copy additional Python service files from root (if they exist)
# These files may or may not exist depending on refactoring state
COPY *.py ./

# Copy static files and templates
COPY static/ ./static/

# Create necessary directories
RUN mkdir -p /app/logs /app/temp

# Set proper permissions
RUN chmod -R 755 /app && \
    chmod -R 777 /app/logs /app/temp

# ============================================================================
# Runtime Configuration
# ============================================================================

# Expose ports
# $PORT is set by Cloud Run dynamically
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=5)" || exit 1

# Non-root user for security (optional but recommended)
# Uncomment if you want to run as non-root user
# RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
# USER appuser

# Environment variable for the key.json file path
# This is set via Cloud Run environment variables
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/key.json

# ============================================================================
# Startup Command
# ============================================================================
# Using gunicorn with optimized worker configuration
# - Workers: 1 (can be adjusted based on CPU cores)
# - Threads: 8 (handles concurrent requests efficiently)
# - Timeout: 0 (no timeout for long-running AI operations)
# - Bind: $PORT (Cloud Run provides this dynamically)

CMD exec gunicorn \
    --bind :$PORT \
    --workers 1 \
    --threads 8 \
    --timeout 0 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    app:app
