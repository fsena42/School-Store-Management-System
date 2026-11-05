import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_itemarchive_purchaseorder_requestapprovalitem_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inventoryaudit",
            name="changed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="inventory_audit_entries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="inventoryaudit",
            name="changed_by_staff_id",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventoryaudit",
            name="request_item_id",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventoryaudit",
            name="quantity_delta",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
