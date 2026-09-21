FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.12-slim AS base
# Apply available Debian security fixes before producing either stage.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM base
RUN useradd --uid 10001 --create-home app
WORKDIR /app
COPY --from=build --chown=10001:10001 /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT=streamable-http MCP_AUTH_MODE=oauth PORT=8080
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "pluggy_finance_mcp"]
