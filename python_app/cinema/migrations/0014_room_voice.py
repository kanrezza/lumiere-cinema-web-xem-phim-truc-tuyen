from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cinema', '0013_comment_moderation')]

    operations = [
        migrations.AddField(
            model_name='membership', name='voice_session',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='membership', name='voice_seen_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='membership', name='voice_mic_on',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='membership', name='voice_host_muted',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.CreateModel(
            name='RoomVoiceSignal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_session', models.UUIDField()),
                ('recipient_session', models.UUIDField()),
                ('kind', models.CharField(max_length=9)),
                ('payload', models.JSONField()),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cinema.room')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['room', 'recipient', 'recipient_session', 'id'], name='room_voice_pending_idx')]},
        ),
    ]
