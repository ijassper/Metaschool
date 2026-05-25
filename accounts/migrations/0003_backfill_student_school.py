from django.db import migrations, transaction


TEMP_SCHOOL_CODE = "TEMP-UNASSIGNED"


def backfill_student_school(apps, schema_editor):
    School = apps.get_model("accounts", "School")
    Student = apps.get_model("accounts", "Student")

    with transaction.atomic():
        temp_school = None

        students = Student.objects.select_related("teacher", "teacher__school").filter(
            school__isnull=True
        )
        for student in students.iterator():
            teacher_school_id = None
            if student.teacher_id and student.teacher and student.teacher.school_id:
                teacher_school_id = student.teacher.school_id

            if teacher_school_id:
                student.school_id = teacher_school_id
            else:
                if temp_school is None:
                    temp_school, _ = School.objects.get_or_create(
                        code=TEMP_SCHOOL_CODE,
                        defaults={
                            "office": "Unassigned",
                            "name": "Unassigned School",
                            "level": "ETC",
                        },
                    )
                student.school_id = temp_school.id
            student.save(update_fields=["school"])


def clear_backfilled_student_school(apps, schema_editor):
    Student = apps.get_model("accounts", "Student")

    with transaction.atomic():
        Student.objects.update(school=None)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_customuser_is_representative_student_school_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_student_school, clear_backfilled_student_school),
    ]
