FROM python:3.12-slim

# System deps required by Playwright/Chromium on Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer — cached unless pyproject.toml or uv.lock changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Source layer (README.md is required by pyproject.toml as the package description)
COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Install Playwright Chromium + system deps (fonts, nss, etc.)
RUN uv run playwright install --with-deps chromium

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["uv", "run", "yoink"]
