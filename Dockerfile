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
COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
RUN uv pip install --no-cache -r requirements.txt


# --- 2. Final Runtime Stage ---
FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr (crucial for container logs)
ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install runtime system dependencies for OpenCV, OpenBLAS, and Qt/XCB GUI support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libice6 \
    libxext6 \
    libxrender1 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-render0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libx11-xcb1 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Copy application source code
COPY . .

CMD ["python", "main.py"]
