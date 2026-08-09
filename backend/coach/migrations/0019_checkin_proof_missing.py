from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0018_changelog_tour_starts_at_the_start'),
    ]

    operations = [
        migrations.AddField(
            model_name='checkin',
            name='proof_missing',
            field=models.TextField(blank=True),
        ),
    ]
