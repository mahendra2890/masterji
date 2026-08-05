"""Create-or-promote the admin account from DJANGO_SUPERUSER_* env vars.

Unlike `createsuperuser --noinput`, this handles the account already
existing — e.g. created earlier by Google login with the same (unique)
email — by promoting it in place. Idempotent; safe on every boot.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or promote the superuser from DJANGO_SUPERUSER_* env vars."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email:
            self.stdout.write("DJANGO_SUPERUSER_EMAIL not set — skipping.")
            return

        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()

        if user is None:
            if not (username and password):
                self.stdout.write(
                    "No existing user with that email; need USERNAME and "
                    "PASSWORD to create one — skipping."
                )
                return
            user = User.objects.create_superuser(
                username=username, email=email, password=password
            )
            action = "Created"
        else:
            if password:
                user.set_password(password)
            action = "Promoted"

        user.is_staff = True
        user.is_superuser = True
        user.save()
        self.stdout.write(self.style.SUCCESS(f"{action} admin: {user.username}"))
