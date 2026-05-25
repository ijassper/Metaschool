from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_backfill_student_school"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE accounts_customuser "
                "MODIFY is_representative bool NOT NULL DEFAULT 0"
            ),
            reverse_sql=(
                "ALTER TABLE accounts_customuser "
                "MODIFY is_representative bool NOT NULL"
            ),
        ),
    ]
