from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('cinema', '0018_waf_behavior')]

    operations = [
        migrations.AddField(
            model_name='order',
            name='checkout_key',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]
