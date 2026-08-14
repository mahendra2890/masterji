"""Two tables that hold a name, a code, and who agreed to be counted.

Schema only, and additive only. Nothing existing is altered, no row is
rewritten, and `gates.py` does not know either of these tables exists — a
cohort is a lens over rows the product already keeps, so the numbers on its
board are the same counts the builder's own dashboard shows.

Numbered 0084, and it took three tries to get there — which is the argument for
checking the leaf again immediately before merging rather than only before
pushing. This was written as 0081, moved to 0083 to leave room for two sessions
holding 0081 (#98) and 0082 (#96) that had not pushed, and repointed onto 0082
when #96 landed mid-build. Then #98 landed too — renumbered to 0083 itself, the
number this file was sitting on. Both depended on 0082, so merging would have
put two leaves on `main` and `migrate` would have refused: the deploy stops for
everybody, and nothing about the diff would have hinted why.

Leaving a gap is not protection. The number a branch is holding is invisible
until it merges, so the only check that works is the one run last.
"""

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models

import coach.models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0083_the_one_number_they_watch'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Cohort',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=120)),
                ('join_code', models.CharField(default=coach.models.mint_join_code, max_length=32, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
                'abstract': False,
                'base_manager_name': 'all_objects',
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('all_objects', django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name='CohortMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('cohort', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='coach.cohort')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cohort_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['joined_at'],
                'abstract': False,
                'base_manager_name': 'all_objects',
                'constraints': [models.UniqueConstraint(condition=models.Q(('deleted_at__isnull', True)), fields=('cohort', 'user'), name='one_membership_per_cohort_per_user')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('all_objects', django.db.models.manager.Manager()),
            ],
        ),
    ]
