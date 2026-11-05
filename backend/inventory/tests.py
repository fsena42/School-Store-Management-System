from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    Department,
    Grn,
    Item,
    Position,
    Purchase,
    PurchaseItem,
    Request,
    RequestItem,
    Staff,
    StaffAccount,
    Status,
    Store,
    Supplier,
    Unit,
)


LEGACY_MODELS = [
    Department,
    Store,
    Unit,
    Position,
    Status,
    Staff,
    Item,
    Request,
    RequestItem,
    Supplier,
    Purchase,
    PurchaseItem,
    Grn,
]


class StoreWorkflowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as schema_editor:
            for model in LEGACY_MODELS:
                schema_editor.create_model(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with connection.schema_editor() as schema_editor:
            for model in reversed(LEGACY_MODELS):
                schema_editor.delete_model(model)

    def setUp(self):
        self.store = Store.objects.create(
            storeid=3,
            storename="Scholastics Store",
        )
        self.unit = Unit.objects.create(
            unitid=1,
            unitname="Each",
            description="Individual item",
        )
        self.department = Department.objects.create(
            departmentid=1,
            departmentname="General",
        )
        self.positions = {
            position_id: Position.objects.create(
                positionid=position_id,
                positionname=name,
            )
            for position_id, name in (
                (1, "Teacher"),
                (5, "Principal"),
                (6, "Deputy Principal"),
                (7, "Store Manager"),
                (8, "Procurement Officer"),
            )
        }
        self.statuses = {
            name.lower(): Status.objects.create(statusname=name)
            for name in (
                "Pending",
                "Approved",
                "Rejected",
                "Partially Issued",
                "Issued",
                "Draft",
            )
        }
        self.item = Item.objects.create(
            itemid=1,
            itemname="Ruler",
            unitid=self.unit,
            quantity=5,
            reorderlevel=2,
            storeid=self.store,
        )
        self.teacher, self.teacher_client = self.make_staff(1, "teacher")
        self.principal, self.principal_client = self.make_staff(5, "principal")
        self.deputy, self.deputy_client = self.make_staff(6, "deputy")
        self.manager, self.manager_client = self.make_staff(7, "manager")
        self.procurement, self.procurement_client = self.make_staff(8, "procurement")

    def make_staff(self, position_id, username):
        staff = Staff.objects.create(
            surname=username.title(),
            othernames="Test",
            departmentid=self.department,
            positionid=self.positions[position_id],
            contact="0000000000",
        )
        user = get_user_model().objects.create_user(
            username=username,
            password="test-password",
        )
        StaffAccount.objects.create(user=user, staff=staff)
        client = APIClient()
        client.force_authenticate(user=user)
        return staff, client

    def test_workflow_tables_are_consolidated_into_existing_tables(self):
        table_names = {
            table.name.lower()
            for table in connection.introspection.get_table_list(
                connection.cursor()
            )
        }
        self.assertTrue({
            "item",
            "purchase",
            "purchase_item",
            "request",
            "request_item",
            "staff",
            "inventory_audit",
        }.issubset(table_names))
        self.assertTrue({
            "item_archive",
            "purchase_order",
            "purchase_order_line",
            "purchase_order_receipt",
            "request_approval_item",
            "request_decision",
            "request_issue",
            "request_legacy_review",
            "staff_contact",
        }.isdisjoint(table_names))

    def make_request(self, quantity=10, status_name="Pending", old_issued=0):
        req = Request.objects.create(
            storeid=self.store,
            staffid=self.teacher,
            requestdate=date.today(),
            statusid=self.statuses[status_name.lower()],
        )
        line = RequestItem.objects.create(
            requestid=req,
            itemid=self.item,
            qtyrequested=quantity,
            qtyissued=old_issued,
        )
        return req, line

    def test_dashboard_and_page_read_apis_work_for_each_role(self):
        requests_page = [
            "/api/requestable-items/",
            "/api/my-requests/",
        ]
        principal_pages = [
            "/api/dashboard/",
            "/api/inventory/",
            "/api/pending-requests/",
            "/api/pending-purchase-orders/",
            "/api/request-issue-history/",
            "/api/purchase-orders/",
            "/api/reports/",
            "/api/management/staff/",
            "/api/management/items/",
            "/api/management/suppliers/",
        ]
        manager_pages = [
            "/api/dashboard/",
            "/api/inventory/",
            "/api/pending-issues/",
            "/api/request-issue-history/",
            "/api/purchase-orders/",
            "/api/receiving/options/",
            "/api/reports/",
            "/api/management/staff/",
            "/api/management/items/",
            "/api/management/suppliers/",
        ]

        for path in requests_page:
            response = self.teacher_client.get(path)
            self.assertEqual(
                response.status_code,
                200,
                f"Teacher GET {path} failed: {response.content[:500]!r}",
            )

        for path in principal_pages:
            response = self.principal_client.get(path)
            self.assertEqual(
                response.status_code,
                200,
                f"Principal GET {path} failed: {response.content[:500]!r}",
            )

        for path in manager_pages:
            response = self.manager_client.get(path)
            self.assertEqual(
                response.status_code,
                200,
                f"Store Manager GET {path} failed: {response.content[:500]!r}",
            )

    def test_approval_is_separate_from_issue_and_issue_updates_stock(self):
        req, line = self.make_request(quantity=4)
        response = self.principal_client.post(
            f"/api/requests/{req.requestid}/approve/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity_approved": 4,
                }],
                "reason": "Approved for classroom use.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)
        self.assertEqual(line.qtyissued, 0)

        response = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 3,
                }],
                "comments": "Collected by requester.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        line.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual(self.item.quantity, 2)
        self.assertEqual(line.qtyissued, 3)
        self.assertEqual(req.statusid.statusname, "Partially Issued")

        response = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 1,
                }],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        req.refresh_from_db()
        self.assertEqual(self.item.quantity, 1)
        self.assertEqual(req.statusid.statusname, "Issued")

    def test_overstock_request_is_allowed_but_issue_is_limited_by_stock(self):
        req, line = self.make_request(quantity=100)
        approved = self.principal_client.post(
            f"/api/requests/{req.requestid}/approve/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity_approved": 100,
                }],
            },
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        too_many = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 6,
                }],
            },
            format="json",
        )
        self.assertEqual(too_many.status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

        partial = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 5,
                }],
            },
            format="json",
        )
        self.assertEqual(partial.status_code, 200, partial.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

        Item.objects.filter(pk=self.item.pk).update(quantity=20)
        self.item.refresh_from_db()
        response = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 20,
                }],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

        Item.objects.filter(pk=self.item.pk).update(quantity=75)
        response = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 75,
                }],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 0)

    def test_approval_and_issuing_permissions_are_separate(self):
        req, line = self.make_request(quantity=2)
        approve_payload = {
            "items": [{
                "request_item_id": line.requestitemid,
                "quantity_approved": 2,
            }],
        }
        self.assertEqual(
            self.manager_client.post(
                f"/api/requests/{req.requestid}/approve/",
                approve_payload,
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.teacher_client.get("/api/pending-issues/").status_code,
            403,
        )
        self.assertEqual(
            self.principal_client.post(
                f"/api/requests/{req.requestid}/issue/",
                {"items": [{"request_item_id": line.requestitemid, "quantity": 1}]},
                format="json",
            ).status_code,
            403,
        )

    def test_rejection_requires_and_records_reason(self):
        req, _ = self.make_request()
        missing_reason = self.principal_client.post(
            f"/api/requests/{req.requestid}/reject/",
            {},
            format="json",
        )
        self.assertEqual(missing_reason.status_code, 400)
        rejected = self.principal_client.post(
            f"/api/requests/{req.requestid}/reject/",
            {"reason": "The request is outside the budget."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(
            Request.objects.get(pk=req.pk).statusid.statusname,
            "Rejected",
        )

    def test_legacy_reconciliation_does_not_change_stock_and_enables_safe_issue(self):
        req, line = self.make_request(
            quantity=8,
            status_name="Approved",
            old_issued=6,
        )
        response = self.manager_client.post(
            f"/api/requests/{req.requestid}/legacy-review/",
            {
                "reason": "Checked signed issue voucher.",
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity_approved": 8,
                    "quantity_previously_issued": 6,
                }],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 5)

        issue = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 2,
                }],
            },
            format="json",
        )
        self.assertEqual(issue.status_code, 200, issue.data)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 3)

    def test_staff_invitation_setup_session_and_logout(self):
        created = self.manager_client.post(
            "/api/management/staff/",
            {
                "surname": "New",
                "othernames": "Staff Member",
                "contact": "1234567890",
                "email": "new.staff@example.test",
                "department_id": self.department.departmentid,
                "position_id": 1,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(len(mail.outbox), 1)

        setup_url = next(
            part for part in mail.outbox[0].body.split()
            if part.startswith("http://localhost:5173?setup=1")
        )
        setup_query = parse_qs(urlparse(setup_url).query)
        password = "A-very-unique-pass-92!"
        setup = APIClient().post(
            "/api/account/setup/",
            {
                "uid": setup_query["uid"][0],
                "token": setup_query["token"][0],
                "password": password,
            },
            format="json",
        )
        self.assertEqual(setup.status_code, 200, setup.data)

        login = APIClient()
        signed_in = login.post(
            "/api/login/",
            {"staff_id": created.data["staff_id"], "password": password},
            format="json",
        )
        self.assertEqual(signed_in.status_code, 200, signed_in.data)
        self.assertTrue(login.get("/api/session/").data["authenticated"])
        self.assertEqual(login.post("/api/logout/").status_code, 200)
        self.assertEqual(login.get("/api/session/").status_code, 403)

    def test_item_archive_waits_for_approved_issue_and_can_be_restored(self):
        req, line = self.make_request(quantity=2)
        approved = self.principal_client.post(
            f"/api/requests/{req.requestid}/approve/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity_approved": 2,
                }],
            },
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.data)

        archive_url = f"/api/management/items/{self.item.itemid}/archive/"
        blocked = self.manager_client.post(
            archive_url,
            {"action": "ARCHIVED", "reason": "Retiring this stock item."},
            format="json",
        )
        self.assertEqual(blocked.status_code, 409)

        issued = self.manager_client.post(
            f"/api/requests/{req.requestid}/issue/",
            {
                "items": [{
                    "request_item_id": line.requestitemid,
                    "quantity": 2,
                }],
            },
            format="json",
        )
        self.assertEqual(issued.status_code, 200, issued.data)
        archived = self.manager_client.post(
            archive_url,
            {"action": "ARCHIVED", "reason": "Retiring this stock item."},
            format="json",
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertNotIn(
            self.item.itemid,
            {
                item["item_id"]
                for item in self.teacher_client.get(
                    "/api/requestable-items/"
                ).data["items"]
            },
        )

        restored = self.manager_client.post(
            archive_url,
            {"action": "RESTORED", "reason": "The item is needed again."},
            format="json",
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertIn(
            self.item.itemid,
            {
                item["item_id"]
                for item in self.teacher_client.get(
                    "/api/requestable-items/"
                ).data["items"]
            },
        )

    def test_purchase_order_requires_approval_and_supports_partial_receipts(self):
        supplier = Supplier.objects.create(
            supplierid=1,
            suppliername="Test supplier",
            contact="0000000000",
            email="supplier@example.test",
            address="Test address",
        )
        order_payload = {
            "order_number": "PO-TEST-1",
            "store_id": self.store.storeid,
            "supplier_id": supplier.supplierid,
            "order_date": date.today().isoformat(),
            "expected_date": None,
            "notes": "",
            "items": [{
                "item_id": self.item.itemid,
                "quantity": 8,
                "unit_cost": "2.50",
            }],
        }
        created = self.procurement_client.post(
            "/api/purchase-orders/",
            order_payload,
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        order_id = created.data["purchase_order"]["purchase_order_id"]

        decision = self.principal_client.post(
            f"/api/purchase-orders/{order_id}/decision/",
            {"decision": "APPROVED"},
            format="json",
        )
        self.assertEqual(decision.status_code, 200, decision.data)

        def receive(quantity, invoice, grn):
            return self.manager_client.post(
                "/api/receiving/receive/",
                {
                    "purchase_order_id": order_id,
                    "store_id": self.store.storeid,
                    "supplier_id": supplier.supplierid,
                    "invoice_number": invoice,
                    "invoice_date": date.today().isoformat(),
                    "purchase_date": date.today().isoformat(),
                    "grn_number": grn,
                    "grn_date": date.today().isoformat(),
                    "items": [{
                        "item_id": self.item.itemid,
                        "quantity": quantity,
                        "unit_cost": "2.50",
                    }],
                },
                format="json",
            )

        first = receive(3, "INV-TEST-1", "GRN-TEST-1")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(
            first.data["purchase_order_status"],
            "Partially Received",
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 8)

        second = receive(5, "INV-TEST-2", "GRN-TEST-2")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(second.data["purchase_order_status"], "Received")
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 13)
