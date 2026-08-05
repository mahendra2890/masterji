FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

# Manifest static storage needs no DB; dummy env just for this step
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=0 \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "start.sh"]
