from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0022_changelog_the_day_is_closed_not_empty'),
    ]

    operations = [
        migrations.AddField(
            model_name='checkin',
            name='proof_missing',
            field=models.TextField(blank=True),
        ),
    ]
