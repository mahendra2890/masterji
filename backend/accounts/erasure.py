"""Leaving — the one thing this product had no route for.

Everything else here is about coming back tomorrow. That is exactly why the
way out has to be real: this database holds a teenager's daily work diary,
the nights that were not about the work, and what they said about their
parents and their failures. A product that keeps all of that and offers no
door is asking for a kind of trust it has not earned, and India's DPDP Act
makes erasure an expectation rather than a courtesy.

The shape follows the house convention rather than inventing one. Rows are
SOFT deleted — stamped and hidden from every default manager — because
`common/soft_delete.py` has said since the first model that admin is the
only place a row truly leaves. What is NOT soft is the identity: the email,
the username and the password are overwritten on the way out, because a
tombstone that still holds the address is not erasure, and because a unique
email held by a dead row would refuse the same person a fresh account
forever.
"""

from django.db import transaction
from django.utils import timezone
from loguru import logger

from common.soft_delete import SoftDeleteModel


def _descend(obj, stamp, counts: dict[str, int], seen: set) -> None:
    """Soft-delete everything hanging off `obj`, depth first.

    Walked from the model graph rather than written out as a list of models,
    and that is a decision worth defending. A hand-written cascade is correct
    on the day it is written and silently wrong the first time somebody adds a
    model — and the failure is invisible: the rows simply keep answering
    queries for an account that asked to be gone. This cannot miss one.

    `all_objects` on the way down, so a row soft-deleted earlier is still
    traversed and its children are reached; the count only includes rows this
    call actually stamped.
    """
    key = (obj._meta.label, obj.pk)
    if key in seen:
        # No self-referential FK exists today. One is proposed (#63's pivot
        # link), and a cascade that loops forever the day it lands is not a
        # thing to leave for that PR to discover.
        return
    seen.add(key)
    for rel in obj._meta.related_objects:
        model = rel.related_model
        if not issubclass(model, SoftDeleteModel):
            continue
        rows = model.all_objects.filter(**{rel.field.name: obj})
        for child in rows:
            _descend(child, stamp, counts, seen)
        stamped = rows.filter(deleted_at__isnull=True).update(deleted_at=stamp)
        if stamped:
            counts[model._meta.label] = counts.get(model._meta.label, 0) + stamped


@transaction.atomic
def erase(user) -> dict[str, int]:
    """Erase one account. Returns what was stamped, per model, for the log.

    Atomic because a half-erased account is the worst of both: the builder has
    been told they are gone and their evenings are still answering queries.

    The user row itself stays, scrubbed. `is_active = False` is the kill
    switch and it is the built-in one — simplejwt's own `get_user` refuses an
    inactive user, so every access token minted for this account, including
    ones already in a browser, stops authenticating the moment this commits.
    There is no token blacklist in this deployment to add them to, and this
    does the same job without one.
    """
    stamp = timezone.now()
    counts: dict[str, int] = {}
    _descend(user, stamp, counts, set())

    user.is_active = False
    # Freed rather than kept. `email` is unique, so a tombstone still holding
    # it would refuse this person a new account with the same Google address
    # for good — which turns "delete my account" into "ban me", a promise
    # nobody made. Scrubbing it is also the half of this that is actually
    # erasure: the rest of the record is hidden, and this is gone.
    user.email = f"deleted-{user.pk}@deleted.invalid"
    user.username = f"deleted-{user.pk}"
    user.first_name = ""
    user.last_name = ""
    user.set_unusable_password()
    user.save(
        update_fields=[
            "is_active",
            "email",
            "username",
            "first_name",
            "last_name",
            "password",
        ]
    )
    logger.info(f"Account {user.pk} erased: {counts or 'no rows'}")
    return counts
