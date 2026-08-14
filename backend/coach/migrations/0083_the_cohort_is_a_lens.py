"""Two tables that hold a name, a code, and who agreed to be counted.

Schema only, and additive only. Nothing existing is altered, no row is
rewritten, and `gates.py` does not know either of these tables exists — a
cohort is a lens over rows the product already keeps, so the numbers on its
board are the same counts the builder's own dashboard shows.

Numbered 0083 with 0081 skipped, and the gap is the point rather than an
accident. Two sessions were mid-build on 0081 (#98) and 0082 (#96) when this
branched and neither had pushed, so `main`'s graph could not show either — the
one collision in this repository that leaves a visible artifact, and the
cheapest possible fix is to not take a number somebody is already holding.
0082 landed while this was being built and this was repointed onto it; 0081 is
still in flight in an open pull request, and depending on 0082 puts this after
it either way.
"""

import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models

import coach.models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0082_the_hour_they_named'),
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
