FROM node:22-bookworm-slim AS codex
RUN npm install -g --prefix /opt/codex @openai/codex@0.170.0

FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /opt/codex /opt/codex
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH=/app/.venv/bin:/opt/codex/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra app --no-install-project
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra app && codex --version
