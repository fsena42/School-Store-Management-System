from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_itemarchive_purchaseorder_requestapprovalitem_and_more"),
    ]

    operations = [
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
