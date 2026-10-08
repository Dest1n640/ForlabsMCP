FROM ghcr.io/astral-sh/uv:0.12.23-python3.11-alpine3.23 AS builder

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.11-alpine3.23 AS runtime
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/forlabs \
    FORLABS_TOKEN_FILE=/app/forlabs-session.json
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN mkdir -p /home/forlabs/.local/state/forlabs-mcp \
    && chown -R 65532:65532 /home/forlabs
USER 65532:65532
ENTRYPOINT ["forlabs-mcp"]
