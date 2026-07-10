FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY src ./src
COPY alembic ./alembic

RUN uv sync --frozen --no-dev
