"""The two things an accepted proof now says about itself: who it was about,
and which parts of the phase's bar it satisfied.

Written as 0053 off 0052, renumbered to 0054 when PR #107 landed
0053_changelog_the_commit_is_priced_honestly under this branch mid-flight. The
rebase reported success and left TWO leaves off 0052 — git has no opinion about
migration graphs, so `dependencies` points at what actually landed.

Both columns are additive and nullable-by-default: every proof banked before
today reads as blank, which gates.accepted_proofs counts as its own person and
gates.kinds_owed counts as no kind. Nobody's gate moves backwards on deploy.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("coach", "0053_changelog_the_commit_is_priced_honestly")]

    operations = [
        migrations.AddField(
            model_name="checkin",
            name="proof_parts",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="checkin",
            name="subject",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
