from django.db import migrations


def convert_legacy_activity_tables_to_utf8mb4(apps, schema_editor):
    """평가·활동의 모든 레거시 문자열 열에서 4바이트 문자를 허용한다."""
    connection = schema_editor.connection
    if connection.vendor != 'mysql':
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT TABLE_NAME
              FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE()
               AND TABLE_TYPE = 'BASE TABLE'
               AND LEFT(TABLE_NAME, 11) = %s
               AND (TABLE_COLLATION IS NULL OR TABLE_COLLATION NOT LIKE %s)
             ORDER BY TABLE_NAME
            """,
            ['activities_', 'utf8mb4%'],
        )
        table_names = [row[0] for row in cursor.fetchall()]

    quote_name = connection.ops.quote_name
    for table_name in table_names:
        schema_editor.execute(
            'ALTER TABLE {} CONVERT TO CHARACTER SET utf8mb4 '
            'COLLATE utf8mb4_unicode_ci'.format(quote_name(table_name))
        )


class Migration(migrations.Migration):
    # MySQL은 ALTER TABLE을 롤백할 수 없으므로 트랜잭션 밖에서 실행한다.
    atomic = False

    dependencies = [
        ('activities', '0049_normalize_2026_attendance_folder'),
    ]

    operations = [
        migrations.RunPython(
            convert_legacy_activity_tables_to_utf8mb4,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
