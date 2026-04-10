FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./

RUN pip install --no-cache-dir poetry \
    && poetry install --no-ansi --no-root

COPY . .

RUN mkdir -p /app/logs /app/media \
    && chmod +x docker/entrypoint-web.sh docker/entrypoint-bot.sh

EXPOSE 8000
