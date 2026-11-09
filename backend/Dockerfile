FROM ghcr.io/astral-sh/uv:0.11.19 AS uv
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra voice --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --extra voice && useradd --create-home --uid 10001 app && mkdir -p /var/lib/brightwater/media /home/app/.cache && chown app:app /var/lib/brightwater/media /home/app/.cache
USER app
EXPOSE 8787
CMD ["uvicorn", "brightwater.api:app", "--host", "0.0.0.0", "--port", "8787"]
