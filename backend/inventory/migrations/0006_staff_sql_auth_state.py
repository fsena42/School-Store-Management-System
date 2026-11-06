from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0005_consolidate_workflow_tables"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="staff",
                    name="password_hash",
                    field=models.CharField(
                        blank=True,
                        db_column="PasswordHash",
                        default="!",
                        max_length=256,
                    ),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="is_active",
                    field=models.BooleanField(db_column="IsActive", default=True),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="setup_token_hash",
                    field=models.CharField(
                        blank=True,
                        db_column="SetupTokenHash",
                        max_length=64,
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="setup_token_expires_at",
                    field=models.DateTimeField(
                        blank=True,
                        db_column="SetupTokenExpiresAt",
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="session_token_hash",
                    field=models.CharField(
                        blank=True,
                        db_column="SessionTokenHash",
                        max_length=64,
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="session_expires_at",
                    field=models.DateTimeField(
                        blank=True,
                        db_column="SessionExpiresAt",
                        null=True,
                    ),
                ),
            ],
        ),
    ]
