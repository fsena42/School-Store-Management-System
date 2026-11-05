from decimal import Decimal

from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


def refuse_unsafe_reverse(apps, schema_editor):
    raise IrreversibleError(
        "Workflow data was merged into existing tables. Restore a database "
        "backup to reverse this migration."
    )


def _columns(connection, table_name):
    with connection.cursor() as cursor:
        return {
            column.name.lower()
            for column in connection.introspection.get_table_description(
                cursor, table_name
            )
        }


def add_existing_table_fields(apps, schema_editor):
    connection = schema_editor.connection
    tables = {
        table.name.lower()
        for table in connection.introspection.get_table_list(
            connection.cursor()
        )
    }

    fields = {
        "Item": [
            ("is_archived", models.BooleanField(
                db_column="IsArchived", default=False
            )),
            ("archived_by_staff_id", models.IntegerField(
                db_column="ArchivedBy", blank=True, null=True
            )),
            ("archived_at", models.DateTimeField(
                db_column="ArchivedAt", blank=True, null=True
            )),
            ("archive_reason", models.TextField(
                db_column="ArchiveReason", blank=True, null=True
            )),
        ],
        "Purchase": [
            ("transaction_type", models.CharField(
                db_column="TransactionType", max_length=12, default="RECEIPT"
            )),
            ("parent_purchase", None),
            ("order_number", models.CharField(
                db_column="OrderNumber", max_length=30, blank=True,
                null=True, unique=True,
            )),
            ("order_status", models.CharField(
                db_column="OrderStatus", max_length=20, blank=True, default=""
            )),
            ("approved_by_staff_id", models.IntegerField(
                db_column="ApprovedBy", blank=True, null=True
            )),
            ("expected_date", models.DateField(
                db_column="ExpectedDate", blank=True, null=True
            )),
            ("notes", models.TextField(db_column="Notes", blank=True, default="")),
            ("rejection_reason", models.TextField(
                db_column="RejectionReason", blank=True, default=""
            )),
        ],
        "Request": [
            ("decision_reason", models.TextField(
                db_column="DecisionReason", blank=True, default=""
            )),
            ("decided_at", models.DateTimeField(
                db_column="DecidedAt", blank=True, null=True
            )),
            ("legacy_review_reason", models.TextField(
                db_column="LegacyReviewReason", blank=True, default=""
            )),
            ("legacy_reviewed_by_id", models.IntegerField(
                db_column="LegacyReviewedBy", blank=True, null=True
            )),
            ("legacy_reviewed_at", models.DateTimeField(
                db_column="LegacyReviewedAt", blank=True, null=True
            )),
        ],
        "RequestItem": [
            ("quantity_approved", models.IntegerField(
                db_column="QtyApproved", blank=True, null=True
            )),
        ],
        "Staff": [
            ("email", models.EmailField(
                db_column="Email", max_length=254,
                blank=True, null=True, unique=True,
            )),
        ],
    }

    purchase_model = apps.get_model("inventory", "Purchase")
    fields["Purchase"][1] = (
        "parent_purchase",
        models.ForeignKey(
            purchase_model,
            models.DO_NOTHING,
            db_column="ParentPurchaseID",
            blank=True,
            null=True,
            related_name="receipts",
        ),
    )

    for model_name, model_fields in fields.items():
        model = apps.get_model("inventory", model_name)
        table_name = model._meta.db_table
        if table_name.lower() not in tables:
            continue
        existing_columns = _columns(connection, table_name)
        for field_name, field in model_fields:
            column_name = field.db_column or field_name
            if column_name.lower() in existing_columns:
                continue
            model.add_to_class(field_name, field)
            schema_editor.add_field(model, field)
            existing_columns.add(column_name.lower())


def migrate_legacy_rows(apps, schema_editor):
    connection = schema_editor.connection
    alias = connection.alias
    tables = {
        table.name.lower()
        for table in connection.introspection.get_table_list(
            connection.cursor()
        )
    }
    if "item" not in tables or "request" not in tables or "purchase" not in tables:
        return

    quote = connection.ops.quote_name

    def execute(sql, params=()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def fetchone(sql, params=()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def insert_audit(
        item_id, item_name, action, field_changed, comments, changed_at,
        staff_id, request_item_id=None, quantity_delta=0,
        old_value="", new_value="",
    ):
        request_item_clause = (
            f"{quote('request_item_id')} IS NULL"
            if request_item_id is None
            else f"{quote('request_item_id')} = %s"
        )
        audit_params = [
            item_id, action, field_changed, comments, changed_at, staff_id,
        ]
        if request_item_id is not None:
            audit_params.append(request_item_id)
        audit_params.append(quantity_delta)
        existing = fetchone(
            f"SELECT 1 FROM {quote('inventory_audit')} "
            f"WHERE {quote('item_id')} = %s AND {quote('action')} = %s "
            f"AND {quote('field_changed')} = %s "
            f"AND {quote('comments')} = %s "
            f"AND {quote('changed_at')} = %s "
            f"AND {quote('changed_by_staff_id')} = %s "
            f"AND {request_item_clause} "
            f"AND {quote('quantity_delta')} = %s",
            audit_params,
        )
        if existing:
            return
        execute(
            f"INSERT INTO {quote('inventory_audit')} "
            f"({quote('item_id')}, {quote('item_name')}, "
            f"{quote('action')}, {quote('field_changed')}, "
            f"{quote('old_value')}, {quote('new_value')}, "
            f"{quote('comments')}, {quote('changed_at')}, "
            f"{quote('changed_by_id')}, "
            f"{quote('changed_by_staff_id')}, "
            f"{quote('request_item_id')}, "
            f"{quote('quantity_delta')}) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                item_id, item_name, action, field_changed, old_value,
                new_value, comments, changed_at, None, staff_id,
                request_item_id, quantity_delta,
            ],
        )

    if "staff_contact" in tables:
        StaffContact = apps.get_model("inventory", "StaffContact")
        for contact in StaffContact.objects.using(alias).all().iterator():
            execute(
                f"UPDATE {quote('staff')} SET {quote('Email')} = %s "
                f"WHERE {quote('StaffID')} = %s",
                [contact.email, contact.staff_id],
            )

    if "item_archive" in tables:
        ItemArchive = apps.get_model("inventory", "ItemArchive")
        latest_by_item = {}
        old_states = {}
        for archive in ItemArchive.objects.using(alias).order_by(
            "item_id", "archived_at", "id"
        ).iterator():
            old_state = old_states.get(archive.item_id, False)
            new_state = archive.action == "ARCHIVED"
            item_row = fetchone(
                f"SELECT {quote('ItemName')} FROM {quote('item')} "
                f"WHERE {quote('ItemID')} = %s",
                [archive.item_id],
            )
            item_name = item_row[0] if item_row else "Unknown item"
            insert_audit(
                archive.item_id, item_name, archive.action, "is_archived",
                archive.reason, archive.archived_at,
                archive.archived_by_staff_id, old_value=str(old_state),
                new_value=str(new_state),
            )
            old_states[archive.item_id] = new_state
            latest_by_item[archive.item_id] = archive
        for item_id, archive in latest_by_item.items():
            archived = archive.action == "ARCHIVED"
            execute(
                f"UPDATE {quote('item')} SET {quote('IsArchived')} = %s, "
                f"{quote('ArchivedBy')} = %s, {quote('ArchivedAt')} = %s, "
                f"{quote('ArchiveReason')} = %s "
                f"WHERE {quote('ItemID')} = %s",
                [
                    archived,
                    archive.archived_by_staff_id if archived else None,
                    archive.archived_at if archived else None,
                    archive.reason if archived else None,
                    item_id,
                ],
            )

    if "request_decision" in tables:
        RequestDecision = apps.get_model("inventory", "RequestDecision")
        for decision in RequestDecision.objects.using(alias).all().iterator():
            execute(
                f"UPDATE {quote('request')} SET {quote('ApprovedBy')} = %s, "
                f"{quote('DecisionReason')} = %s, {quote('DecidedAt')} = %s "
                f"WHERE {quote('RequestID')} = %s",
                [
                    decision.decided_by_staff_id, decision.reason,
                    decision.decided_at, decision.request_id,
                ],
            )

    if "request_approval_item" in tables:
        RequestApprovalItem = apps.get_model(
            "inventory", "RequestApprovalItem"
        )
        for approval in RequestApprovalItem.objects.using(alias).all().iterator():
            execute(
                f"UPDATE {quote('request_item')} "
                f"SET {quote('QtyApproved')} = %s "
                f"WHERE {quote('RequestItemID')} = %s",
                [approval.quantity_approved, approval.request_item_id],
            )

    if "request_legacy_review" in tables:
        RequestLegacyReview = apps.get_model(
            "inventory", "RequestLegacyReview"
        )
        reviews_by_request = {}
        for review in RequestLegacyReview.objects.using(alias).order_by(
            "reviewed_at", "id"
        ).iterator():
            line = fetchone(
                f"SELECT {quote('RequestID')}, {quote('ItemID')}, "
                f"{quote('QtyIssued')} FROM {quote('request_item')} "
                f"WHERE {quote('RequestItemID')} = %s",
                [review.request_item_id],
            )
            if line is None:
                continue
            request_id, item_id, issued = line
            execute(
                f"UPDATE {quote('request_item')} SET {quote('QtyIssued')} = %s "
                f"WHERE {quote('RequestItemID')} = %s",
                [
                    max(issued, review.quantity_previously_issued),
                    review.request_item_id,
                ],
            )
            reviews_by_request.setdefault(request_id, []).append(review)
        for request_id, reviews in reviews_by_request.items():
            latest = reviews[-1]
            execute(
                f"UPDATE {quote('request')} SET "
                f"{quote('LegacyReviewReason')} = %s, "
                f"{quote('LegacyReviewedBy')} = %s, "
                f"{quote('LegacyReviewedAt')} = %s, "
                f"{quote('DecidedAt')} = %s "
                f"WHERE {quote('RequestID')} = %s",
                [
                    "\n".join(review.reason for review in reviews),
                    latest.reviewed_by_staff_id, latest.reviewed_at,
                    latest.reviewed_at, request_id,
                ],
            )
        for review in RequestLegacyReview.objects.using(alias).all().iterator():
            line = fetchone(
                f"SELECT {quote('ItemID')} FROM {quote('request_item')} "
                f"WHERE {quote('RequestItemID')} = %s",
                [review.request_item_id],
            )
            if line is None:
                continue
            item_id = line[0]
            item_row = fetchone(
                f"SELECT {quote('ItemName')} FROM {quote('item')} "
                f"WHERE {quote('ItemID')} = %s",
                [item_id],
            )
            insert_audit(
                item_id, item_row[0] if item_row else "Unknown item",
                "LEGACY_REVIEW", "request", review.reason,
                review.reviewed_at, review.reviewed_by_staff_id,
                request_item_id=review.request_item_id,
                quantity_delta=review.quantity_previously_issued,
            )

    if "request_issue" in tables:
        RequestIssue = apps.get_model("inventory", "RequestIssue")
        totals = {}
        for issue in RequestIssue.objects.using(alias).all().iterator():
            totals[issue.request_item_id] = (
                totals.get(issue.request_item_id, 0) + issue.quantity
            )
        for request_item_id, total in totals.items():
            line = fetchone(
                f"SELECT {quote('QtyIssued')} FROM {quote('request_item')} "
                f"WHERE {quote('RequestItemID')} = %s",
                [request_item_id],
            )
            if line is not None and total > line[0]:
                execute(
                    f"UPDATE {quote('request_item')} "
                    f"SET {quote('QtyIssued')} = %s "
                    f"WHERE {quote('RequestItemID')} = %s",
                    [total, request_item_id],
                )
        for issue in RequestIssue.objects.using(alias).all().iterator():
            item_row = fetchone(
                f"SELECT {quote('ItemName')} FROM {quote('item')} "
                f"WHERE {quote('ItemID')} = %s",
                [issue.item_id],
            )
            insert_audit(
                issue.item_id, item_row[0] if item_row else "Unknown item",
                "ISSUE", "quantity", issue.comments, issue.issued_at,
                issue.issued_by_staff_id,
                request_item_id=issue.request_item_id,
                quantity_delta=issue.quantity,
            )

    if "purchase_order" in tables:
        PurchaseOrder = apps.get_model("inventory", "PurchaseOrder")
        PurchaseOrderLine = apps.get_model("inventory", "PurchaseOrderLine")
        PurchaseOrderReceipt = apps.get_model(
            "inventory", "PurchaseOrderReceipt"
        )
        max_line = fetchone(
            f"SELECT MAX({quote('PurchaseItemID')}) "
            f"FROM {quote('purchase_item')}"
        )
        next_line_id = max_line[0] or 0
        purchase_ids = {}

        for order in PurchaseOrder.objects.using(alias).order_by("id").iterator():
            lines = list(
                PurchaseOrderLine.objects.using(alias).filter(
                    purchase_order_id=order.pk
                )
            )
            total = sum(
                (
                    Decimal(line.unit_cost) * line.quantity_ordered
                    for line in lines
                ),
                Decimal("0.000"),
            ).quantize(Decimal("0.001"))
            invoice_number = f"OLDPO{order.pk}"
            existing_order = fetchone(
                f"SELECT {quote('PurchaseID')} FROM {quote('purchase')} "
                f"WHERE {quote('TransactionType')} = %s "
                f"AND {quote('OrderNumber')} = %s",
                ["ORDER", order.order_number],
            )
            if existing_order:
                purchase_id = existing_order[0]
            else:
                suffix = 1
                while fetchone(
                    f"SELECT 1 FROM {quote('purchase')} "
                    f"WHERE {quote('InvoiceNumber')} = %s",
                    [invoice_number],
                ):
                    invoice_number = f"OLDPO{order.pk}-{suffix}"
                    suffix += 1
                columns = [
                    "StoreID", "SupplierID", "StaffID", "InvoiceNumber",
                    "InvoiceDate", "PurchaseDate", "TotalAmount",
                    "TransactionType", "ParentPurchaseID", "OrderNumber",
                    "OrderStatus", "ApprovedBy", "ExpectedDate", "Notes",
                    "RejectionReason",
                ]
                values = [
                    order.store_id, order.supplier_id,
                    order.created_by_staff_id, invoice_number,
                    order.order_date, order.order_date, total,
                    "ORDER", None, order.order_number, order.status,
                    order.approved_by_staff_id, order.expected_date,
                    order.notes, order.rejection_reason,
                ]
                sql = (
                    f"INSERT INTO {quote('purchase')} "
                    f"({', '.join(quote(column) for column in columns)}) "
                    f"VALUES ({', '.join(['%s'] * len(values))})"
                )
                purchase_id = execute(sql, values)
            purchase_ids[order.pk] = purchase_id

            for line in lines:
                existing_line = fetchone(
                    f"SELECT {quote('PurchaseItemID')} "
                    f"FROM {quote('purchase_item')} "
                    f"WHERE {quote('PurchaseID')} = %s "
                    f"AND {quote('ItemID')} = %s",
                    [purchase_id, line.item_id],
                )
                if existing_line:
                    execute(
                        f"UPDATE {quote('purchase_item')} "
                        f"SET {quote('UnitCost')} = %s, "
                        f"{quote('Quantity')} = %s "
                        f"WHERE {quote('PurchaseItemID')} = %s",
                        [
                            line.unit_cost, line.quantity_ordered,
                            existing_line[0],
                        ],
                    )
                else:
                    next_line_id += 1
                    execute(
                        f"INSERT INTO {quote('purchase_item')} "
                        f"({quote('PurchaseItemID')}, {quote('PurchaseID')}, "
                        f"{quote('ItemID')}, {quote('UnitCost')}, "
                        f"{quote('Quantity')}) VALUES (%s, %s, %s, %s, %s)",
                        [
                            next_line_id, purchase_id, line.item_id,
                            line.unit_cost, line.quantity_ordered,
                        ],
                    )

        for receipt in PurchaseOrderReceipt.objects.using(alias).all().iterator():
            parent_id = purchase_ids.get(receipt.purchase_order_id)
            if parent_id is None:
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {quote('purchase')} "
                    f"SET {quote('TransactionType')} = %s, "
                    f"{quote('ParentPurchaseID')} = %s "
                    f"WHERE {quote('PurchaseID')} = %s",
                    ["RECEIPT", parent_id, receipt.purchase_id],
                )


def drop_legacy_tables(apps, schema_editor):
    connection = schema_editor.connection
    existing = {
        table.name.lower()
        for table in connection.introspection.get_table_list(
            connection.cursor()
        )
    }
    legacy_models = (
        "PurchaseOrderReceipt",
        "PurchaseOrderLine",
        "RequestIssue",
        "RequestLegacyReview",
        "RequestApprovalItem",
        "RequestDecision",
        "StaffContact",
        "ItemArchive",
        "PurchaseOrder",
    )
    required_tables = {
        "item", "purchase", "purchase_item", "request", "request_item",
        "staff", "inventory_audit",
    }
    if not required_tables.issubset(existing):
        quote = connection.ops.quote_name
        for model_name in legacy_models:
            model = apps.get_model("inventory", model_name)
            table_name = model._meta.db_table
            if table_name.lower() not in existing:
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT 1 FROM {quote(table_name)} LIMIT 1"
                )
                if cursor.fetchone():
                    raise RuntimeError(
                        "Workflow data cannot be consolidated because the "
                        "original store tables are missing. Restore the "
                        "database schema and retry the migration."
                    )
    for model_name in legacy_models:
        model = apps.get_model("inventory", model_name)
        if model._meta.db_table.lower() in existing:
            schema_editor.delete_model(model)


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_inventoryaudit_request_issue_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_existing_table_fields,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="item",
                    name="is_archived",
                    field=models.BooleanField(db_column="IsArchived", default=False),
                ),
                migrations.AddField(
                    model_name="item",
                    name="archived_by_staff_id",
                    field=models.IntegerField(
                        blank=True, db_column="ArchivedBy", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="item",
                    name="archived_at",
                    field=models.DateTimeField(
                        blank=True, db_column="ArchivedAt", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="item",
                    name="archive_reason",
                    field=models.TextField(
                        blank=True, db_column="ArchiveReason", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="transaction_type",
                    field=models.CharField(
                        db_column="TransactionType",
                        default="RECEIPT",
                        max_length=12,
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="parent_purchase",
                    field=models.ForeignKey(
                        blank=True,
                        db_column="ParentPurchaseID",
                        null=True,
                        on_delete=models.DO_NOTHING,
                        related_name="receipts",
                        to="inventory.purchase",
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="order_number",
                    field=models.CharField(
                        blank=True,
                        db_column="OrderNumber",
                        max_length=30,
                        null=True,
                        unique=True,
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="order_status",
                    field=models.CharField(
                        blank=True,
                        db_column="OrderStatus",
                        default="",
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="approved_by_staff_id",
                    field=models.IntegerField(
                        blank=True, db_column="ApprovedBy", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="expected_date",
                    field=models.DateField(
                        blank=True, db_column="ExpectedDate", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="notes",
                    field=models.TextField(
                        blank=True, db_column="Notes", default=""
                    ),
                ),
                migrations.AddField(
                    model_name="purchase",
                    name="rejection_reason",
                    field=models.TextField(
                        blank=True, db_column="RejectionReason", default=""
                    ),
                ),
                migrations.AddField(
                    model_name="request",
                    name="decision_reason",
                    field=models.TextField(
                        blank=True, db_column="DecisionReason", default=""
                    ),
                ),
                migrations.AddField(
                    model_name="request",
                    name="decided_at",
                    field=models.DateTimeField(
                        blank=True, db_column="DecidedAt", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="request",
                    name="legacy_review_reason",
                    field=models.TextField(
                        blank=True,
                        db_column="LegacyReviewReason",
                        default="",
                    ),
                ),
                migrations.AddField(
                    model_name="request",
                    name="legacy_reviewed_by_id",
                    field=models.IntegerField(
                        blank=True, db_column="LegacyReviewedBy", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="request",
                    name="legacy_reviewed_at",
                    field=models.DateTimeField(
                        blank=True, db_column="LegacyReviewedAt", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="requestitem",
                    name="quantity_approved",
                    field=models.IntegerField(
                        blank=True, db_column="QtyApproved", null=True
                    ),
                ),
                migrations.AddField(
                    model_name="staff",
                    name="email",
                    field=models.EmailField(
                        blank=True,
                        db_column="Email",
                        max_length=254,
                        null=True,
                        unique=True,
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            migrate_legacy_rows,
            reverse_code=refuse_unsafe_reverse,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    drop_legacy_tables,
                    reverse_code=refuse_unsafe_reverse,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="purchaseorderline",
                    name="purchase_order",
                ),
                migrations.RemoveField(
                    model_name="purchaseorderreceipt",
                    name="purchase_order",
                ),
                migrations.DeleteModel(name="PurchaseOrderReceipt"),
                migrations.DeleteModel(name="PurchaseOrderLine"),
                migrations.DeleteModel(name="ItemArchive"),
                migrations.DeleteModel(name="RequestApprovalItem"),
                migrations.DeleteModel(name="RequestDecision"),
                migrations.DeleteModel(name="RequestIssue"),
                migrations.DeleteModel(name="RequestLegacyReview"),
                migrations.DeleteModel(name="StaffContact"),
                migrations.DeleteModel(name="PurchaseOrder"),
            ],
        ),
    ]
