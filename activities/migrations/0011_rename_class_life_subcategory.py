from django.db import migrations


OLD_SUBCATEGORY = '학급 생활'
NEW_SUBCATEGORY = '생활 교육'


def rename_class_life_subcategory(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(
        category='SCHOOL_LIFE',
        sub_category=OLD_SUBCATEGORY,
    ).update(sub_category=NEW_SUBCATEGORY)


def restore_class_life_subcategory(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(
        category='SCHOOL_LIFE',
        sub_category=NEW_SUBCATEGORY,
    ).update(sub_category=OLD_SUBCATEGORY)


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0010_alter_activity_section_alter_activity_title_and_more'),
    ]

    operations = [
        migrations.RunPython(
            rename_class_life_subcategory,
            restore_class_life_subcategory,
        ),
    ]
