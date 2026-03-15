# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install all runtime dependencies (service extra) but not the project itself.
# --no-install-project defers installing yoink until source is present.
RUN uv sync --frozen --no-install-project --extra service

# Install Playwright's Chromium browser + OS-level system deps.
# Store browsers in /opt/pw-browsers so all users can read them.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN .venv/bin/playwright install chromium --with-deps

# Now copy source + README (referenced in pyproject.toml) and install the project
COPY src/ src/
COPY README.md ./
RUN uv sync --frozen --extra service

# Non-root user for least-privilege operation
RUN useradd --create-home yoink
USER yoink

EXPOSE 8000

ENTRYPOINT ["uv", "run", "yoink"]
CMD ["serve"]
