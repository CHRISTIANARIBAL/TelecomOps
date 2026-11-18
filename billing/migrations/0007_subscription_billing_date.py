from datetime import date

from django.db import migrations, models


def convert_billing_days_to_dates(apps, schema_editor):
    Subscription = apps.get_model("billing", "Subscription")

    for subscription in Subscription.objects.all():
        subscription.billing_date_new = date(
            2026,
            11,
            subscription.billing_day,
        )
        subscription.save(update_fields=["billing_date_new"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0006_alter_internetplan_service_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="billing_date_new",
            field=models.DateField(null=True, blank=True),
        ),

        migrations.RunPython(
            convert_billing_days_to_dates,
            migrations.RunPython.noop,
        ),

        migrations.RemoveField(
            model_name="subscription",
            name="billing_day",
        ),

        migrations.RenameField(
            model_name="subscription",
            old_name="billing_date_new",
            new_name="billing_date",
        ),

        migrations.AlterField(
            model_name="subscription",
            name="billing_date",
            field=models.DateField(),
        ),
    ]