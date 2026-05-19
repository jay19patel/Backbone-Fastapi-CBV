# =============================================================================
# Backbone FastAPI — Production Dockerfile
# =============================================================================
# Multi-stage build:
#   1. builder  — install deps into a virtual env
#   2. runtime  — copy venv, add non-root user, run uvicorn
#
# Build:
#   docker build -t backbone-app .
#
# Run:
#   docker run --env-file .env -p 8000:8000 backbone-app
# =============================================================================

# ── Stage 1: Dependency Builder ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed to build Python packages (motor, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency files first (layer cache optimisation)
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime Image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: Do not run as root
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# PDF invoices use reportlab (Python) — no wkhtmltopdf needed
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source
COPY --chown=appuser:appgroup . .

# Writable dirs for non-root user (file logs, media uploads)
RUN mkdir -p /app/logs /app/media && chown -R appuser:appgroup /app/logs /app/media

# Ensure venv binaries are on PATH
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1

# Switch to non-root user
USER appuser

EXPOSE 8000

# Healthcheck — FastAPI /health endpoint (added in main.py)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Single worker: avoids duplicate Redis task workers per container.
# uvicorn[standard] in requirements.txt provides uvloop + httptools.
CMD ["/opt/venv/bin/uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--http", "httptools"]
