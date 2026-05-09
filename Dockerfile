# ─── Stage 1: build deps (needs gcc for greenlet/SQLAlchemy) ─────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app/ ./app/

# Install production deps only (no [dev]) into a separate prefix
RUN pip install --no-cache-dir --prefix=/deps .

# ─── Stage 2: runtime image (no gcc, no dev deps) ────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# curl is needed for the HEALTHCHECK
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /deps /usr/local

# Copy application source
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Runtime dirs + unprivileged user
RUN mkdir -p data logs \
    && groupadd -r appgroup \
    && useradd -r -g appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:8000/capture/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "app.main"]
