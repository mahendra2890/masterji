from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: username login, unique email, how the coach talks.

    Declared before any real user data exists so AUTH_USER_MODEL never has
    to change mid-project (Django makes that switch very painful later).
    """

    class Tone(models.TextChoices):
        ENGLISH = "ENGLISH", "English"
        HINGLISH = "HINGLISH", "Hinglish"

    class Mode(models.TextChoices):
        """Which side of the table Masterji sits on — the builder's setting,
        not the model's guess.

        COACH is the product: one task, proof tonight, the gate. THINKING is
        for the part of the work that comes before there is anything to
        declare — the builder asks to think it through, and Masterji answers
        with questions and options instead of assignments. Neither one moves
        the gate: gates.py doesn't read this field and never will, which is
        what stops a thinking partner from becoming a way around the door.
        """

        COACH = "COACH", "Coach"
        THINKING = "THINKING", "Thinking partner"

    email = models.EmailField(unique=True)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.ENGLISH)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.COACH)

    # createsuperuser prompts for these in addition to username/password
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = "user"

    def __str__(self):
        return self.username
