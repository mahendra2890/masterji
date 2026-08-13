"""The first four indexes in the project, on the four queries that earn them.

Until this there was not one — no `db_index`, no `Meta.indexes`, nothing but
Django's implicit foreign-key indexes and three conditional `UniqueConstraint`s.

All four are partial, and the predicate is the point. `SoftDeleteManager` puts
`deleted_at IS NULL` on every query through the default manager, so as a
*condition* it costs nothing and keeps each index the size of the live table.
Indexing the `deleted_at` column on its own — the obvious reading of "soft
delete makes everything more expensive" — would have bought nothing: nearly
every row is undeleted, and an index that matches nearly everything is not
worth reading. The changelog index is the same lesson twice, since nearly
every entry is `is_active`, which is why that column is a condition here and
not the leading field.

Schema only. Nothing a builder sees changes and no query is rewritten — these
are the same reads, planned better.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0070_changelog_the_coach_can_see_the_calendar'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddIndex(
            model_name='changelogentry',
            index=models.Index(condition=models.Q(('deleted_at__isnull', True), ('is_active', True)), fields=['-shipped_on', '-id'], name='coach_changelog_live_idx'),
        ),
        migrations.AddIndex(
            model_name='checkin',
            index=models.Index(condition=models.Q(('deleted_at__isnull', True)), fields=['goal', 'phase', 'proof_status'], name='coach_checkin_gate_idx'),
        ),
        migrations.AddIndex(
            model_name='checkin',
            index=models.Index(condition=models.Q(('deleted_at__isnull', True)), fields=['goal', 'date', '-created_at'], name='coach_checkin_day_idx'),
        ),
        migrations.AddIndex(
            model_name='goal',
            index=models.Index(condition=models.Q(('deleted_at__isnull', True)), fields=['user', 'status'], name='coach_goal_active_idx'),
        ),
    ]
