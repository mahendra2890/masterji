from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: username login, unique email, coach tone preference.

    Declared before any real user data exists so AUTH_USER_MODEL never has
    to change mid-project (Django makes that switch very painful later).
    """

    class Tone(models.TextChoices):
        ENGLISH = "ENGLISH", "English"
        HINGLISH = "HINGLISH", "Hinglish"

    email = models.EmailField(unique=True)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.ENGLISH)

    # createsuperuser prompts for these in addition to username/password
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "user"

    def __str__(self):
        return self.username
