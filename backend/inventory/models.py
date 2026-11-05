# -*- coding: cp1252 -*-

# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.


from django.db import models


class Department(models.Model):
    departmentid = models.IntegerField(db_column='DepartmentID', primary_key=True, db_comment='Unique identifier for a department ')  # Field name made lowercase.
    departmentname = models.CharField(db_column='DepartmentName', max_length=100, db_comment='Name of department ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'department'


class Grn(models.Model):
    grnid = models.AutoField(db_column='GRNID', primary_key=True, db_comment='Unique identifier for the GRN ')  # Field name made lowercase.
    purchaseid = models.OneToOneField('Purchase', models.DO_NOTHING, db_column='PurchaseID', db_comment='Purchase being received; one GRN at most per purchase')  # Field name made lowercase.
    grnnumber = models.CharField(db_column='GRNNumber', unique=True, max_length=50, db_comment='Unique GRN document number ')  # Field name made lowercase.
    grndate = models.DateField(db_column='GRNDate', db_comment='Date the goods were received ')  # Field name made lowercase.
    staffid = models.ForeignKey('Staff', models.DO_NOTHING, db_column='StaffID', db_comment='Staff member who received the goods ')  # Field name made lowercase.
    remarks = models.CharField(db_column='Remarks', max_length=255, db_comment='Additional information about the delivery ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'grn'


class Item(models.Model):
    itemid = models.IntegerField(db_column='ItemID', primary_key=True, db_comment='Unique identifier for each item ')  # Field name made lowercase.
    itemname = models.CharField(db_column='ItemName', max_length=100, db_comment='Name of item ')  # Field name made lowercase.
    unitid = models.ForeignKey('Unit', models.DO_NOTHING, db_column='UnitID', db_comment='Unit of item measurement; references UNIT(UnitID) ')  # Field name made lowercase.
    quantity = models.IntegerField(db_column='Quantity', db_comment='Current quantity of item in stock ')  # Field name made lowercase.
    reorderlevel = models.IntegerField(db_column='ReorderLevel', db_comment='Minimum stock level before reordering ')  # Field name made lowercase.
    storeid = models.ForeignKey('Store', models.DO_NOTHING, db_column='StoreID', db_comment='Identifies the store where the item belongs ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'item'


class Position(models.Model):
    positionid = models.IntegerField(db_column='PositionID', primary_key=True, db_comment='Unique identifier for a position ')  # Field name made lowercase.
    positionname = models.CharField(db_column='PositionName', max_length=100, db_comment='Name of staff position ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'position'


class Purchase(models.Model):
    purchaseid = models.AutoField(db_column='PurchaseID', primary_key=True, db_comment='Unique identifier for each purchase made ')  # Field name made lowercase.
    storeid = models.ForeignKey('Store', models.DO_NOTHING, db_column='StoreID', db_comment='Store for which the purchase is made; references STORE ')  # Field name made lowercase.
    supplierid = models.ForeignKey('Supplier', models.DO_NOTHING, db_column='SupplierID', db_comment='Supplier who provided the purchase ')  # Field name made lowercase.
    staffid = models.ForeignKey('Staff', models.DO_NOTHING, db_column='StaffID', db_comment='Staff member responsible for the purchase ')  # Field name made lowercase.
    invoicenumber = models.CharField(db_column='InvoiceNumber', unique=True, max_length=20, db_comment='Unique number on the supplier�s invoice ')  # Field name made lowercase.
    invoicedate = models.DateField(db_column='InvoiceDate', db_comment='Date on supplier invoice ')  # Field name made lowercase.
    purchasedate = models.DateField(db_column='PurchaseDate', db_comment='Date on which the purchase was made ')  # Field name made lowercase.
    totalamount = models.DecimalField(db_column='TotalAmount', max_digits=12, decimal_places=3, db_comment='Total monetary value of the purchase ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'purchase'


class PurchaseItem(models.Model):
    purchaseitemid = models.IntegerField(
        db_column='PurchaseItemID',
        primary_key=True,
        db_comment='Unique identifier for a purchase line ',
    )
    purchaseid = models.ForeignKey(
        Purchase,
        models.DO_NOTHING,
        db_column='PurchaseID',
    )
    itemid = models.ForeignKey(
        Item,
        models.DO_NOTHING,
        db_column='ItemID',
    )
    unitcost = models.DecimalField(
        db_column='UnitCost',
        max_digits=12,
        decimal_places=2,
    )
    quantity = models.IntegerField(
        db_column='Quantity',
    )
    subtotal = models.GeneratedField(
        expression=models.F('unitcost') * models.F('quantity'),
        output_field=models.DecimalField(
            max_digits=12,
            decimal_places=2,
        ),
        db_persist=True,
        db_column='Subtotal',
    )

    class Meta:
        managed = False
        db_table = 'purchase_item'


class Request(models.Model):
    requestid = models.AutoField(
    db_column='RequestID',
    primary_key=True,
    db_comment='Unique identifier for each request '
    ) # Field name made lowercase.
    storeid = models.ForeignKey('Store', models.DO_NOTHING, db_column='StoreID', db_comment='Store for which the request is made; references STORE ')  # Field name made lowercase.
    staffid = models.ForeignKey('Staff', models.DO_NOTHING, db_column='StaffID', db_comment='Staff member who made the request ')  # Field name made lowercase.
    requestdate = models.DateField(db_column='RequestDate', db_comment='Date on which request was made ')  # Field name made lowercase.
    statusid = models.ForeignKey('Status', models.DO_NOTHING, db_column='StatusID', db_comment='Current status of request; references STATUS ')  # Field name made lowercase.
    approvedby = models.ForeignKey('Staff', models.DO_NOTHING, db_column='ApprovedBy', related_name='request_approvedby_set', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'request'


class RequestItem(models.Model):
    requestitemid = models.AutoField(
    db_column='RequestItemID',
    primary_key=True,
    db_comment='Unique identifier for a requested item '
    )
    requestid = models.ForeignKey(Request, models.DO_NOTHING, db_column='RequestID', db_comment='Request to which the item belongs ')  # Field name made lowercase.
    itemid = models.ForeignKey(Item, models.DO_NOTHING, db_column='ItemID', db_comment='Item being requested ')  # Field name made lowercase.
    qtyrequested = models.IntegerField(db_column='QtyRequested', db_comment='Quantity requested by the staff member ')  # Field name made lowercase.
    qtyissued = models.IntegerField(db_column='QtyIssued', db_comment='Quantity actually issued ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'request_item'


class Staff(models.Model):
    staffid = models.AutoField(db_column='StaffID', primary_key=True, db_comment='Unique identifier for each staff member ')  # Field name made lowercase.
    surname = models.CharField(db_column='SurName', max_length=50, db_comment='Surname of a staff member')  # Field name made lowercase.
    othernames = models.CharField(db_column='OtherNames', max_length=100, db_comment='Staff member�s other names ')  # Field name made lowercase.
    departmentid = models.ForeignKey(Department, models.DO_NOTHING, db_column='DepartmentID', db_comment='Department where staff member belongs; references DEPARTMENT ')  # Field name made lowercase.
    positionid = models.ForeignKey(Position, models.DO_NOTHING, db_column='PositionID', db_comment='Staff member�s position; references position')  # Field name made lowercase.
    contact = models.CharField(db_column='Contact', max_length=20, db_comment=' Staff member�s contact ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'staff'


class Status(models.Model):
    statusid = models.AutoField(db_column='StatusID', primary_key=True, db_comment='Unique identifier for a request status ')  # Field name made lowercase.
    statusname = models.CharField(db_column='StatusName', max_length=30, db_comment='Name of the request status ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'status'


class Store(models.Model):
    storeid = models.AutoField(db_column='StoreID', primary_key=True, db_comment='Unique identifier for each store ')  # Field name made lowercase.
    storename = models.CharField(db_column='StoreName', max_length=100, db_comment='Name of store ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'store'


class Supplier(models.Model):
    supplierid = models.IntegerField(db_column='SupplierID', primary_key=True, db_comment='Unique identifier for each supplier ')  # Field name made lowercase.
    suppliername = models.CharField(db_column='SupplierName', max_length=100, db_comment='Name of supplier ')  # Field name made lowercase.
    contact = models.CharField(db_column='Contact', max_length=20, db_comment='Supplier contact number ')  # Field name made lowercase.
    email = models.CharField(db_column='Email', max_length=100, blank=True, null=True, db_comment='Supplier email address ')  # Field name made lowercase.
    address = models.CharField(db_column='Address', max_length=100, db_comment='Supplier physical address ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'supplier'


class Unit(models.Model):
    unitid = models.IntegerField(db_column='UnitID', primary_key=True, db_comment='Unique identifier for a unit ')  # Field name made lowercase.
    unitname = models.CharField(db_column='UnitName', max_length=50, db_comment='Name of measurement unit ')  # Field name made lowercase.
    description = models.CharField(db_column='Description', max_length=200, db_comment='Explanation of unit ')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'unit'


from django.conf import settings

class StaffAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_account",
    )

    staff = models.OneToOneField(
        Staff,
        on_delete=models.PROTECT,
        related_name="login_account",
        db_column="StaffID",
    )

    class Meta:
        db_table = "staff_account"


from django.conf import settings
from django.db import models


class InventoryAudit(models.Model):
    audit_id = models.AutoField(primary_key=True)

    item_id = models.IntegerField()
    item_name = models.CharField(max_length=255)

    action = models.CharField(max_length=20)
    field_changed = models.CharField(max_length=100, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    comments = models.TextField()

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inventory_audit_entries",
    )

    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_audit"
        ordering = ["-changed_at"]


class RequestDecision(models.Model):
    request_id = models.IntegerField(unique=True)
    decision = models.CharField(max_length=10)
    reason = models.TextField()
    decided_by_staff_id = models.IntegerField()
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "request_decision"


class RequestApprovalItem(models.Model):
    request_item_id = models.IntegerField(unique=True)
    quantity_approved = models.PositiveIntegerField()

    class Meta:
        db_table = "request_approval_item"


class RequestIssue(models.Model):
    request_item_id = models.IntegerField()
    item_id = models.IntegerField()
    quantity = models.PositiveIntegerField()
    issued_by_staff_id = models.IntegerField()
    comments = models.TextField(blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "request_issue"
        indexes = [
            models.Index(fields=["request_item_id", "issued_at"]),
        ]


class RequestLegacyReview(models.Model):
    request_item_id = models.IntegerField(unique=True)
    quantity_previously_issued = models.PositiveIntegerField()
    reviewed_by_staff_id = models.IntegerField()
    reason = models.TextField()
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "request_legacy_review"


class ItemArchive(models.Model):
    item_id = models.IntegerField()
    action = models.CharField(max_length=10)
    archived_by_staff_id = models.IntegerField()
    reason = models.TextField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "item_archive"
        indexes = [
            models.Index(fields=["item_id", "archived_at"]),
        ]


class StaffContact(models.Model):
    staff_id = models.IntegerField(unique=True)
    email = models.EmailField(unique=True)

    class Meta:
        db_table = "staff_contact"


class PurchaseOrder(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_PENDING = "Pending"
    STATUS_APPROVED = "Approved"
    STATUS_PARTIALLY_RECEIVED = "Partially Received"
    STATUS_RECEIVED = "Received"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, STATUS_DRAFT),
        (STATUS_PENDING, STATUS_PENDING),
        (STATUS_APPROVED, STATUS_APPROVED),
        (STATUS_PARTIALLY_RECEIVED, STATUS_PARTIALLY_RECEIVED),
        (STATUS_RECEIVED, STATUS_RECEIVED),
        (STATUS_REJECTED, STATUS_REJECTED),
    ]

    order_number = models.CharField(max_length=30, unique=True)
    store_id = models.IntegerField()
    supplier_id = models.IntegerField()
    created_by_staff_id = models.IntegerField()
    approved_by_staff_id = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    order_date = models.DateField()
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchase_order"
        ordering = ["-created_at"]


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    item_id = models.IntegerField()
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "purchase_order_line"
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "item_id"],
                name="unique_purchase_order_item",
            ),
        ]


class PurchaseOrderReceipt(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    purchase_id = models.IntegerField(unique=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "purchase_order_receipt"
