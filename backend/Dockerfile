FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
# --compile-bytecode, and no PYTHONDONTWRITEBYTECODE above it, because this
# image is *started* far more often than it is built: Render replaces the
# container on every deploy and again on every wake from spin-down, and the
# health check a deploy waits on cannot pass until Python has finished
# importing. Without a cached .pyc the ~2,600 modules in this venv recompile
# from source every one of those times, and litellm is on the boot path rather
# than the request path — settings.MIDDLEWARE registers LlmBudgetMiddleware,
# which imports it. Paying the compile once here, in a layer Render already
# caches, measured ~40% off `manage.py check` (10.3s → 6.1s at 2 vCPUs).
#
# The cost is image size, and it is the right trade in this direction: size is
# paid on push and pull once per deploy, compilation was being paid once per
# start.
RUN uv sync --frozen --no-dev --compile-bytecode

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

# The app's own modules, for the same reason. Cheap next to the venv, but the
# 90 migration modules are in here and `migrate` loads all of them on every
# boot to build the graph before it can decide there is nothing to apply.
RUN python -m compileall -q . -x '\.venv'

# Manifest static storage needs no DB; dummy env just for this step
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=0 \
    python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "start.sh"]
