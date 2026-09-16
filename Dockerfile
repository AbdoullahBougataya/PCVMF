# 1. Builder Stage
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast package resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN uv pip install --no-cache -r requirements.txt

# --- 2. Final Runtime Stage ---
FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr (crucial for container logs)
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install runtime system dependencies for OpenCV and OpenBLAS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Copy application source code
COPY . .

CMD ["python", "main.py"]
