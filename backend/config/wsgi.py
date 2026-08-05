import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Tracing hooks into the running process, so it starts with the server —
# after Django is configured, and never for management commands or tests.
from config.tracing import setup_tracing  # noqa: E402

setup_tracing()
