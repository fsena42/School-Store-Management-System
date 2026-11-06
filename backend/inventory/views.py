
from datetime import date, timedelta
import hashlib
import hmac
import json
import logging
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .serializers import RequestSerializer
from .permissions import (
    APPROVER_POSITION_IDS,
    INVENTORY_MAINTAINER_POSITION_IDS,
    INVENTORY_VIEW_POSITION_IDS,
    ISSUER_POSITION_IDS,
    MANAGEMENT_POSITION_IDS,
    PURCHASE_ORDER_APPROVER_POSITION_IDS,
    PURCHASING_POSITION_IDS,
    REQUESTABLE_STORES_BY_POSITION,
)

from decimal import Decimal, InvalidOperation
import smtplib
import uuid
from django.db import IntegrityError
from .authentication import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    new_session_token,
    session_expiry,
    session_token_hash,
)
from .sql import execute, fetch_all, fetch_one, insert

logger = logging.getLogger(__name__)


def load_item_audit_history(value):
    if value in (None, ""):
        return []
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    history = json.loads(value) if isinstance(value, str) else value
    if not isinstance(history, list):
        raise ValueError("Item audit history must be a JSON array.")
    return history


def append_item_audit(
    item_id,
    item_name,
    action,
    field_changed,
    old_value,
    new_value,
    comments,
    changed_by_staff_id,
    request_item_id=None,
    quantity_delta=0,
):
    lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
    item = fetch_one(
        "SELECT AuditHistory FROM item WHERE ItemID = %s" + lock_suffix,
        [item_id],
    )
    if item is None:
        raise IntegrityError("Cannot record audit history for a missing item.")
    history = load_item_audit_history(item["AuditHistory"])
    history.append({
        "audit_id": f"{item_id}:{uuid.uuid4()}",
        "item_id": item_id,
        "item_name": item_name,
        "action": action,
        "field_changed": field_changed,
        "old_value": str(old_value),
        "new_value": str(new_value),
        "comments": comments,
        "changed_by_staff_id": changed_by_staff_id,
        "request_item_id": request_item_id,
        "quantity_delta": quantity_delta,
        "changed_at": timezone.now().isoformat(),
    })
    updated = execute(
        "UPDATE item SET AuditHistory = %s WHERE ItemID = %s",
        [json.dumps(history, separators=(",", ":")), item_id],
    )
    if updated != 1:
        raise IntegrityError("Item audit history could not be saved.")


def sql_full_name(first_name_column, last_name_column):
    if connection.vendor == "mysql":
        return f"CONCAT({first_name_column}, ' ', {last_name_column})"
    return f"({first_name_column} || ' ' || {last_name_column})"


@api_view(["POST"])
@permission_classes([AllowAny])
def staff_login(request):
    staff_id = request.data.get("staff_id")
    password = request.data.get("password")
    if staff_id is None or not isinstance(password, str) or not password:
        return Response({"error": "Staff ID and password are required."}, status=status.HTTP_400_BAD_REQUEST)
    staff_key = str(staff_id).strip()
    if not staff_key.isdigit():
        return Response({"error": "Invalid staff ID or password."}, status=status.HTTP_401_UNAUTHORIZED)
    staff = fetch_one(
        "SELECT s.StaffID, s.SurName, s.OtherNames, s.PositionID, p.PositionName, s.PasswordHash, s.IsActive "
        "FROM staff AS s JOIN position AS p ON p.PositionID = s.PositionID WHERE s.StaffID = %s",
        [int(staff_key)],
    )
    if staff is None or not staff["IsActive"] or not check_password(password, staff["PasswordHash"]):
        return Response({"error": "Invalid staff ID or password."}, status=status.HTTP_401_UNAUTHORIZED)
    token = new_session_token()
    execute(
        "UPDATE staff SET SessionTokenHash = %s, SessionExpiresAt = %s WHERE StaffID = %s AND IsActive = 1",
        [session_token_hash(token), session_expiry(), staff["StaffID"]],
    )
    response = Response({"message": "Login successful.", "staff": {
        "staff_id": staff["StaffID"], "surname": staff["SurName"],
        "othernames": staff["OtherNames"], "position_id": staff["PositionID"],
        "position": staff["PositionName"],
    }})
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_MAX_AGE, httponly=True,
                        secure=not settings.DEBUG, samesite="Lax", path="/")
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_request(request):
    try:
        staff = request.user.staff_account.staff
    except AttributeError:
        return Response(
            {"error": "No staff record is linked to this account."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = RequestSerializer(
        data=request.data,
        context={"staff": staff},
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    pending_status = fetch_one(
        "SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1",
        ["pending"],
    )
    if pending_status is None:
        return Response(
            {"error": "Pending status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = serializer.validated_data

    with transaction.atomic():
        request_id = insert(
            """
            INSERT INTO `request` (StoreID, StaffID, RequestDate, StatusID, ApprovedBy)
            VALUES (%s, %s, %s, %s, NULL)
            """,
            [data["store_id"], staff.staffid, date.today(), pending_status["StatusID"]],
        )
        for item_data in data["items"]:
            execute(
                """
                INSERT INTO request_item (RequestID, ItemID, QtyRequested, QtyIssued)
                VALUES (%s, %s, %s, 0)
                """,
                [request_id, item_data["item_id"], item_data["quantity"]],
            )

    return Response(
        {
            "message": "Request submitted successfully.",
            "request_id": request_id,
            "status": "Pending",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_session(request):
    staff = request.user
    return Response({"authenticated": True, "staff_id": staff.staffid,
                     "name": f"{staff.surname} {staff.othernames}",
                     "position": staff.position})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    execute(
        "UPDATE staff SET SessionTokenHash = NULL, SessionExpiresAt = NULL "
        "WHERE StaffID = %s AND SessionTokenHash = %s",
        [request.user.staffid, session_token_hash(request.auth)],
    )
    response = Response({"message": "Signed out successfully."})
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="Lax")
    return response


def send_account_setup_email(staff_id, email):
    if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
        raise RuntimeError("Email delivery is not configured. Set EMAIL_HOST and DEFAULT_FROM_EMAIL before inviting staff.")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    execute(
        "UPDATE staff SET SetupTokenHash = %s, SetupTokenExpiresAt = %s WHERE StaffID = %s AND IsActive = 1",
        [token_hash, timezone.now() + timedelta(hours=24), staff_id],
    )
    uid = urlsafe_base64_encode(str(staff_id).encode("utf-8"))
    frontend_url = getattr(settings, "FRONTEND_URL", "http://127.0.0.1:5173")
    setup_url = f"{frontend_url.rstrip('/')}?setup=1&uid={uid}&token={token}"
    try:
        send_mail("Set up your school store account",
                  "A school store account was created for you. Open this one-time link to choose a password: " + setup_url,
                  settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    except Exception:
        execute(
            "UPDATE staff SET SetupTokenHash = NULL, SetupTokenExpiresAt = NULL "
            "WHERE StaffID = %s AND SetupTokenHash = %s",
            [staff_id, token_hash],
        )
        raise


def archived_item_ids():
    return {
        row["ItemID"]
        for row in fetch_all("SELECT ItemID FROM item WHERE IsArchived = 1")
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def complete_staff_account_setup(request):
    uid, token, password = (request.data.get("uid"), request.data.get("token"), request.data.get("password"))
    if not all(isinstance(value, str) and value for value in (uid, token, password)):
        return Response({"error": "A valid setup link and password are required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        staff_id = int(urlsafe_base64_decode(uid).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return Response({"error": "This account setup link is invalid or expired."}, status=status.HTTP_400_BAD_REQUEST)
    staff = fetch_one(
        "SELECT StaffID, SetupTokenHash FROM staff WHERE StaffID = %s AND IsActive = 1 AND SetupTokenExpiresAt > %s",
        [staff_id, timezone.now()],
    )
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if staff is None or not staff["SetupTokenHash"] or not hmac.compare_digest(staff["SetupTokenHash"], token_hash):
        return Response({"error": "This account setup link is invalid or expired."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        validate_password(password)
    except ValidationError as error:
        return Response({"error": " ".join(error.messages)}, status=status.HTTP_400_BAD_REQUEST)
    updated = execute(
        "UPDATE staff SET PasswordHash = %s, SetupTokenHash = NULL, SetupTokenExpiresAt = NULL "
        "WHERE StaffID = %s AND SetupTokenHash = %s",
        [make_password(password), staff_id, token_hash],
    )
    if updated != 1:
        return Response({"error": "This account setup link is invalid or expired."}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"message": "Password set. You can now sign in."})


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_token(request):
    return Response({"csrfToken": get_token(request)})



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    try:
        staff = request.user.staff_account.staff
    except AttributeError:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    position_id = staff.positionid_id

    store_ids = REQUESTABLE_STORES_BY_POSITION.get(position_id, ())

    stores = []
    if store_ids:
        placeholders = ", ".join(["%s"] * len(store_ids))
        stores = fetch_all(
            f"SELECT StoreID AS storeid, StoreName AS storename FROM store "
            f"WHERE StoreID IN ({placeholders}) ORDER BY StoreID",
            list(store_ids),
        )

    return Response({
        "staff": {
            "staff_id": staff.staffid,
            "name": f"{staff.surname} {staff.othernames}",
            "position": staff.positionid.positionname,
        },
        "stores": stores,
        "can_approve": position_id in APPROVER_POSITION_IDS,
        "can_issue": position_id in ISSUER_POSITION_IDS,
        "can_manage_purchase_orders": position_id in PURCHASING_POSITION_IDS,
    })



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def inventory_list(request):
    try:
        staff = request.user.staff_account.staff
    except AttributeError:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Only these positions may view inventory:
    # 5 = Principal, 6 = Deputy Principal,
    # 7 = Store Manager, 8 = Procurement Officer.
    if staff.positionid_id not in INVENTORY_VIEW_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to view inventory."},
            status=status.HTTP_403_FORBIDDEN,
        )

    items = fetch_all(
        """
        SELECT i.ItemID, i.ItemName, i.StoreID, s.StoreName,
               i.UnitID, i.Quantity, i.ReorderLevel, i.IsArchived, i.AuditHistory,
               EXISTS (SELECT 1 FROM request_item ri WHERE ri.ItemID = i.ItemID) AS HasRequestHistory,
               EXISTS (SELECT 1 FROM purchase_item pi WHERE pi.ItemID = i.ItemID) AS HasProcurementHistory
        FROM item i
        JOIN store s ON s.StoreID = i.StoreID
        ORDER BY i.ItemID
        """
    )
    results = []
    for item in items:
        has_audit_history = bool(load_item_audit_history(item["AuditHistory"]))
        if item["HasRequestHistory"]:
            delete_block_reason = (
                "This item cannot be deleted because it has request history."
            )
        elif item["HasProcurementHistory"]:
            delete_block_reason = (
                "This item cannot be deleted because it has procurement history."
            )
        elif has_audit_history:
            delete_block_reason = (
                "This item cannot be deleted because it has audit history."
            )
        elif item["IsArchived"]:
            delete_block_reason = (
                "Restore this item before deleting it."
            )
        elif item["Quantity"] != 0:
            delete_block_reason = "Only items with zero stock can be deleted."
        else:
            delete_block_reason = None

        results.append({
            "item_id": item["ItemID"],
            "item_name": item["ItemName"],
            "store_id": item["StoreID"],
            "store_name": item["StoreName"],
            "unit_id": item["UnitID"],
            "quantity": item["Quantity"],
            "reorder_level": item["ReorderLevel"],
            "is_archived": bool(item["IsArchived"]),
            "delete_block_reason": delete_block_reason,
        })

    return Response({
        "staff_id": staff.staffid,
        "items": results,
    })



@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_inventory_item(request, item_id):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response({"error": "Only the Principal or Store Manager can edit inventory."}, status=status.HTTP_403_FORBIDDEN)
    comments = request.data.get("comments")
    if not isinstance(comments, str) or not comments.strip():
        return Response({"error": "A comment explaining the change is required."}, status=status.HTTP_400_BAD_REQUEST)
    item = fetch_one(
        "SELECT ItemID, ItemName, Quantity, ReorderLevel FROM item WHERE ItemID = %s",
        [item_id],
    )
    if item is None:
        return Response({"error": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)

    allowed_fields = {
        "item_name": ("ItemName", "item_name"),
        "quantity": ("Quantity", "quantity"),
        "reorder_level": ("ReorderLevel", "reorder_level"),
    }
    changes = {key: request.data[key] for key in allowed_fields if key in request.data}
    if not changes:
        return Response({"error": "Provide at least one field to update."}, status=status.HTTP_400_BAD_REQUEST)

    validated = {}
    for api_field, value in changes.items():
        if api_field == "item_name":
            if not isinstance(value, str) or not value.strip():
                return Response({"error": "Item name must not be empty."}, status=status.HTTP_400_BAD_REQUEST)
            validated[api_field] = value.strip()
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return Response({"error": f"{api_field} must be a non-negative integer."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            validated[api_field] = value

    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        item = fetch_one(
            "SELECT ItemID, ItemName, Quantity, ReorderLevel FROM item WHERE ItemID = %s" + lock_suffix,
            [item_id],
        )
        if item is None:
            return Response({"error": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)
        for api_field, new_value in validated.items():
            column, audit_field = allowed_fields[api_field]
            old_value = item[column]
            if old_value == new_value:
                continue
            updated = execute(
                f"UPDATE item SET {column} = %s WHERE ItemID = %s AND {column} = %s",
                [new_value, item_id, old_value],
            )
            if updated != 1:
                return Response({"error": "Inventory item changed before the update could be saved."}, status=status.HTTP_409_CONFLICT)
            append_item_audit(
                item_id=item_id,
                item_name=item["ItemName"],
                action="STOCK_ADJUSTMENT" if api_field == "quantity" else "EDIT",
                field_changed=audit_field,
                old_value=old_value,
                new_value=new_value,
                comments=comments.strip(),
                changed_by_staff_id=staff.staffid,
            )
            item[column] = new_value

    updated_item = fetch_one(
        "SELECT ItemID, ItemName, Quantity, ReorderLevel FROM item WHERE ItemID = %s",
        [item_id],
    )
    return Response({
        "message": "Inventory item updated successfully.",
        "item": {
            "item_id": updated_item["ItemID"],
            "item_name": updated_item["ItemName"],
            "quantity": updated_item["Quantity"],
            "reorder_level": updated_item["ReorderLevel"],
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_requests(request):
    staff = request.user.staff_account.staff
    requests = fetch_all(
        """
        SELECT r.RequestID, r.StoreID, st.StoreName, r.RequestDate,
               r.StatusID, s.StatusName, r.DecisionReason, r.DecidedAt,
               r.LegacyReviewedAt
        FROM `request` r
        JOIN store st ON st.StoreID = r.StoreID
        JOIN status s ON s.StatusID = r.StatusID
        WHERE r.StaffID = %s
        ORDER BY r.RequestDate DESC, r.RequestID DESC
        """,
        [staff.staffid],
    )
    results = []
    for req in requests:
        legacy_decision = (
            req["StatusName"].lower() in {"approved", "partially issued", "issued"}
            and req["DecidedAt"] is None
            and req["LegacyReviewedAt"] is None
        )
        lines = fetch_all(
            """
            SELECT ri.RequestItemID, ri.ItemID, i.ItemName, ri.QtyRequested,
                   ri.QtyIssued, ri.QtyApproved
            FROM request_item ri
            JOIN item i ON i.ItemID = ri.ItemID
            WHERE ri.RequestID = %s
            ORDER BY ri.RequestItemID
            """,
            [req["RequestID"]],
        )
        results.append({
            "request_id": req["RequestID"],
            "store_id": req["StoreID"],
            "store_name": req["StoreName"],
            "request_date": req["RequestDate"],
            "status_id": req["StatusID"],
            "status": req["StatusName"],
            "decision_reason": req["DecisionReason"],
            "legacy_review_required": legacy_decision,
            "items": [
                {
                    "request_item_id": line["RequestItemID"],
                    "item_id": line["ItemID"],
                    "item_name": line["ItemName"],
                    "quantity_requested": line["QtyRequested"],
                    "quantity_approved": None if legacy_decision else (line["QtyApproved"] or 0),
                    "quantity_issued": line["QtyIssued"],
                    "quantity_remaining": 0 if legacy_decision else max(0, (line["QtyApproved"] or 0) - line["QtyIssued"]),
                    "legacy_review_required": legacy_decision,
                    "legacy_quantity_recorded": line["QtyIssued"] if legacy_decision else None,
                }
                for line in lines
            ],
        })
    return Response({"requests": results})


def legacy_approval_requires_review(req):
    status_name = req["statusname"] if isinstance(req, dict) else req.statusid.statusname
    decided_at = req["decided_at"] if isinstance(req, dict) else req.decided_at
    reviewed_at = req["legacy_reviewed_at"] if isinstance(req, dict) else req.legacy_reviewed_at
    return (
        status_name.lower() in {"approved", "partially issued", "issued"}
        and decided_at is None
        and reviewed_at is None
    )


def request_item_summary(line, legacy_review_required=False):
    if isinstance(line, dict):
        request_item_id = line["requestitemid"]
        item_id = line["itemid_id"]
        item_name = line["itemname"]
        requested = line["qtyrequested"]
        issued = line["qtyissued"]
        quantity_approved = line["quantity_approved"]
    else:
        request_item_id = line.requestitemid
        item_id = line.itemid_id
        item_name = line.itemid.itemname
        requested = line.qtyrequested
        issued = line.qtyissued
        quantity_approved = line.quantity_approved
    if legacy_review_required:
        approved = None
        remaining = 0
    else:
        approved = quantity_approved or 0
        remaining = max(0, approved - issued)

    return {
        "request_item_id": request_item_id,
        "item_id": item_id,
        "item_name": item_name,
        "quantity_requested": requested,
        "quantity_approved": approved,
        "quantity_issued": issued,
        "quantity_remaining": remaining,
        "legacy_review_required": legacy_review_required,
        "legacy_quantity_recorded": issued if legacy_review_required else None,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_request_draft(request):
    staff = request.user.staff_account.staff
    serializer = RequestSerializer(data=request.data, context={"staff": staff})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    draft_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["draft"])
    if draft_status is None:
        return Response({"error": "Draft status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    data = serializer.validated_data
    with transaction.atomic():
        request_id = insert(
            "INSERT INTO `request` (StoreID, StaffID, RequestDate, StatusID, ApprovedBy) VALUES (%s, %s, %s, %s, NULL)",
            [data["store_id"], staff.staffid, date.today(), draft_status["StatusID"]],
        )
        for item_data in data["items"]:
            execute("INSERT INTO request_item (RequestID, ItemID, QtyRequested, QtyIssued) VALUES (%s, %s, %s, 0)",
                    [request_id, item_data["item_id"], item_data["quantity"]])
    return Response({"message": "Draft saved successfully.", "request_id": request_id, "status": "Draft"}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_request_draft(request, request_id):
    staff = request.user.staff_account.staff
    draft = fetch_one(
        "SELECT r.RequestID, r.StoreID, s.StatusName FROM `request` r JOIN status s ON s.StatusID = r.StatusID WHERE r.RequestID = %s AND r.StaffID = %s",
        [request_id, staff.staffid],
    )
    if draft is None:
        return Response({"error": "Draft not found."}, status=status.HTTP_404_NOT_FOUND)
    if draft["StatusName"].lower() != "draft":
        return Response({"error": "Only drafts can be edited."}, status=status.HTTP_400_BAD_REQUEST)
    serializer = RequestSerializer(data=request.data, context={"staff": staff})
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    data = serializer.validated_data
    with transaction.atomic():
        execute("UPDATE `request` SET StoreID = %s WHERE RequestID = %s AND StaffID = %s",
                [data["store_id"], request_id, staff.staffid])
        execute("DELETE FROM request_item WHERE RequestID = %s", [request_id])
        for item_data in data["items"]:
            execute("INSERT INTO request_item (RequestID, ItemID, QtyRequested, QtyIssued) VALUES (%s, %s, %s, 0)",
                    [request_id, item_data["item_id"], item_data["quantity"]])
    return Response({"message": "Draft updated successfully.", "request_id": request_id, "status": "Draft"})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_request_draft(request, request_id):
    staff = request.user.staff_account.staff
    draft = fetch_one(
        "SELECT r.RequestID, s.StatusName FROM `request` r JOIN status s ON s.StatusID = r.StatusID WHERE r.RequestID = %s AND r.StaffID = %s",
        [request_id, staff.staffid],
    )
    if draft is None:
        return Response({"error": "Draft not found."}, status=status.HTTP_404_NOT_FOUND)
    if draft["StatusName"].lower() != "draft":
        return Response({"error": "Only drafts can be deleted."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        execute("DELETE FROM request_item WHERE RequestID = %s", [request_id])
        execute("DELETE FROM `request` WHERE RequestID = %s AND StaffID = %s", [request_id, staff.staffid])
    return Response({"message": "Draft deleted successfully."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_request_draft(request, request_id):
    staff = request.user.staff_account.staff
    draft = fetch_one(
        "SELECT r.RequestID, r.StoreID, s.StatusName FROM `request` r JOIN status s ON s.StatusID = r.StatusID WHERE r.RequestID = %s AND r.StaffID = %s",
        [request_id, staff.staffid],
    )
    if draft is None:
        return Response({"error": "Draft not found."}, status=status.HTTP_404_NOT_FOUND)
    if draft["StatusName"].lower() != "draft":
        return Response({"error": "Only drafts can be submitted."}, status=status.HTTP_400_BAD_REQUEST)
    pending_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["pending"])
    if pending_status is None:
        return Response({"error": "Pending status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    draft_lines = fetch_all("SELECT ItemID, QtyRequested FROM request_item WHERE RequestID = %s ORDER BY RequestItemID", [request_id])
    if not draft_lines:
        return Response({"error": "A request must contain at least one item."}, status=status.HTTP_400_BAD_REQUEST)
    serializer = RequestSerializer(data={"store_id": draft["StoreID"], "items": [
        {"item_id": line["ItemID"], "quantity": line["QtyRequested"]} for line in draft_lines
    ]}, context={"staff": staff})
    if not serializer.is_valid():
        return Response({"error": "This draft is no longer valid. Update it before submitting.", "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    updated = execute(
        "UPDATE `request` SET StatusID = %s WHERE RequestID = %s AND StaffID = %s AND StatusID = %s",
        [pending_status["StatusID"], request_id, staff.staffid, fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["draft"])["StatusID"]],
    )
    if updated != 1:
        return Response({"error": "Draft changed before it could be submitted. Reload and try again."}, status=status.HTTP_409_CONFLICT)
    return Response({"message": "Request submitted successfully.", "request_id": request_id, "status": "Pending"})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def requestable_items(request):
    staff = request.user.staff_account.staff
    store_ids = REQUESTABLE_STORES_BY_POSITION.get(staff.positionid_id, ())
    if not store_ids:
        return Response({"items": []})
    placeholders = ", ".join(["%s"] * len(store_ids))
    items = fetch_all(
        f"SELECT i.ItemID, i.ItemName, i.StoreID, s.StoreName FROM item i "
        f"JOIN store s ON s.StoreID = i.StoreID WHERE i.StoreID IN ({placeholders}) "
        "AND COALESCE(i.IsArchived, 0) = 0 ORDER BY i.ItemID",
        list(store_ids),
    )
    return Response({"items": [{
        "item_id": item["ItemID"], "item_name": item["ItemName"],
        "store_id": item["StoreID"], "store_name": item["StoreName"],
    } for item in items]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_requests(request):
    try:
        staff = request.user.staff_account.staff
    except AttributeError:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Only authorized positions may review requests.
    if staff.positionid_id not in APPROVER_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to review requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    pending_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["pending"])
    if pending_status is None:
        return Response(
            {"error": "Pending status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    pending = fetch_all(
        """
        SELECT r.RequestID AS requestid, r.RequestDate AS requestdate,
               r.StaffID AS staffid_id, st.OtherNames AS othernames,
               st.SurName AS surname, r.StoreID AS storeid_id,
               store.StoreName AS storename, s.StatusName AS statusname
        FROM `request` r
        JOIN staff st ON st.StaffID = r.StaffID
        JOIN store ON store.StoreID = r.StoreID
        JOIN status s ON s.StatusID = r.StatusID
        WHERE r.StatusID = %s
        ORDER BY r.RequestDate, r.RequestID
        """,
        [pending_status["StatusID"]],
    )
    results = []

    for req in pending:
        lines = fetch_all(
            """
            SELECT ri.RequestItemID AS requestitemid, ri.ItemID AS itemid_id,
                   i.ItemName AS itemname, ri.QtyRequested AS qtyrequested,
                   i.Quantity AS quantity
            FROM request_item ri JOIN item i ON i.ItemID = ri.ItemID
            WHERE ri.RequestID = %s ORDER BY ri.RequestItemID
            """,
            [req["requestid"]],
        )

        results.append({
            "request_id": req["requestid"],
            "request_date": req["requestdate"],
            "staff_id": req["staffid_id"],
            "staff_name": f"{req['othernames']} {req['surname']}".strip(),
            "store_id": req["storeid_id"],
            "store_name": req["storename"],
            "status": req["statusname"],
            "items": [
                {
                    "request_item_id": line["requestitemid"],
                    "item_id": line["itemid_id"],
                    "item_name": line["itemname"],
                    "quantity_requested": line["qtyrequested"],
                    "quantity_in_stock": line["quantity"],
                }
                for line in lines
            ],
        })

    return Response({"requests": results})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def request_issue_history(request):
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in (*APPROVER_POSITION_IDS, *ISSUER_POSITION_IDS):
        return Response(
            {"error": "You are not authorized to view request issue progress."},
            status=status.HTTP_403_FORBIDDEN,
        )

    requests = fetch_all(
        f"""
        SELECT r.RequestID AS requestid, r.RequestDate AS requestdate,
               {sql_full_name("st.OtherNames", "st.SurName")} AS requester,
               store.StoreName AS storename, s.StatusName AS statusname,
               r.DecisionReason AS decision_reason, r.DecidedAt AS decided_at,
               r.LegacyReviewedAt AS legacy_reviewed_at
        FROM `request` r
        JOIN status s ON s.StatusID = r.StatusID
        JOIN staff st ON st.StaffID = r.StaffID
        JOIN store ON store.StoreID = r.StoreID
        WHERE LOWER(s.StatusName) <> 'draft'
        ORDER BY r.RequestDate DESC, r.RequestID DESC
        """
    )
    results = []
    for req in requests:
        lines = fetch_all(
            """
            SELECT ri.RequestItemID AS requestitemid, ri.ItemID AS itemid_id,
                   i.ItemName AS itemname, ri.QtyRequested AS qtyrequested,
                   ri.QtyIssued AS qtyissued, ri.QtyApproved AS quantity_approved
            FROM request_item ri JOIN item i ON i.ItemID = ri.ItemID
            WHERE ri.RequestID = %s ORDER BY ri.RequestItemID
            """,
            [req["requestid"]],
        )
        legacy = legacy_approval_requires_review(req)
        results.append({
            "request_id": req["requestid"],
            "request_date": req["requestdate"],
            "requester": req["requester"].strip(),
            "store_name": req["storename"],
            "status": req["statusname"],
            "decision_reason": req["decision_reason"],
            "legacy_review_required": legacy,
            "items": [
                request_item_summary(line, legacy)
                for line in lines
            ],
        })
    return Response({"requests": results})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_request(request, request_id):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in APPROVER_POSITION_IDS:
        return Response({"error": "You are not authorized to approve requests."}, status=status.HTTP_403_FORBIDDEN)
    approved_items = request.data.get("items")
    reason = request.data.get("reason", "")
    if not isinstance(reason, str):
        return Response({"error": "Approval notes must be text."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(approved_items, list) or not approved_items:
        return Response({"error": "Provide the approved quantity for each requested item."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        req = fetch_one(
            "SELECT r.RequestID, r.StatusID, s.StatusName, r.DecidedAt, r.LegacyReviewedAt "
            "FROM `request` r JOIN status s ON s.StatusID = r.StatusID "
            "WHERE r.RequestID = %s" + lock_suffix,
            [request_id],
        )
        if req is None:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        if req["StatusName"].lower() != "pending":
            return Response({"error": "Only pending requests can be approved."}, status=status.HTTP_400_BAD_REQUEST)
        if req["DecidedAt"] is not None or req["LegacyReviewedAt"] is not None:
            return Response({"error": "This request already has a recorded decision."}, status=status.HTTP_409_CONFLICT)
        lines = fetch_all(
            "SELECT RequestItemID, ItemID, QtyRequested FROM request_item WHERE RequestID = %s ORDER BY RequestItemID" + lock_suffix,
            [request_id],
        )
        if not lines:
            return Response({"error": "This request has no items."}, status=status.HTTP_400_BAD_REQUEST)
        submitted = {}
        for entry in approved_items:
            if not isinstance(entry, dict):
                return Response({"error": "Invalid item quantity data."}, status=status.HTTP_400_BAD_REQUEST)
            item_id = entry.get("request_item_id")
            quantity = entry.get("quantity_approved")
            if isinstance(item_id, bool) or not isinstance(item_id, int) or isinstance(quantity, bool) or not isinstance(quantity, int):
                return Response({"error": "Item IDs and quantities must be integers."}, status=status.HTTP_400_BAD_REQUEST)
            if item_id in submitted:
                return Response({"error": "Duplicate request item."}, status=status.HTTP_400_BAD_REQUEST)
            submitted[item_id] = quantity
        expected_ids = {line["RequestItemID"] for line in lines}
        if set(submitted) != expected_ids:
            return Response({"error": "Submit an approved quantity for every item in this request."}, status=status.HTTP_400_BAD_REQUEST)
        if not any(submitted[line["RequestItemID"]] > 0 for line in lines):
            return Response({"error": "Approve at least one item quantity, or reject the request."}, status=status.HTTP_400_BAD_REQUEST)
        for line in lines:
            quantity = submitted[line["RequestItemID"]]
            if quantity < 0 or quantity > line["QtyRequested"]:
                return Response({"error": f"Approved quantity for item {line['ItemID']} must be between 0 and {line['QtyRequested']}."}, status=status.HTTP_400_BAD_REQUEST)
        new_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["approved"])
        if new_status is None:
            return Response({"error": "Approved status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        for line in lines:
            execute("UPDATE request_item SET QtyApproved = %s WHERE RequestItemID = %s", [submitted[line["RequestItemID"]], line["RequestItemID"]])
        updated = execute(
            "UPDATE `request` SET StatusID = %s, ApprovedBy = %s, DecisionReason = %s, DecidedAt = %s "
            "WHERE RequestID = %s AND StatusID = %s",
            [new_status["StatusID"], staff.staffid, reason.strip(), timezone.now(), request_id, req["StatusID"]],
        )
        if updated != 1:
            return Response({"error": "Request changed before approval could be saved."}, status=status.HTTP_409_CONFLICT)
    return Response({
        "message": "Request quantities approved. The Store Manager must issue stock separately.",
        "request_id": request_id,
        "status": "Approved",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_issues(request):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response({"error": "Only the Store Manager can issue approved stock."}, status=status.HTTP_403_FORBIDDEN)
    pending = fetch_all(
        f"SELECT r.RequestID AS requestid, r.RequestDate AS requestdate, "
        f"{sql_full_name('st.OtherNames', 'st.SurName')} AS requester, store.StoreName AS storename, "
        "s.StatusName AS statusname, r.DecidedAt AS decided_at, r.LegacyReviewedAt AS legacy_reviewed_at "
        "FROM `request` r JOIN status s ON s.StatusID = r.StatusID "
        "JOIN staff st ON st.StaffID = r.StaffID JOIN store ON store.StoreID = r.StoreID "
        "WHERE LOWER(s.StatusName) IN (%s, %s) ORDER BY r.RequestDate, r.RequestID",
        ["approved", "partially issued"],
    )
    results, legacy_review = [], []
    for req in pending:
        lines = fetch_all(
            "SELECT ri.RequestItemID AS requestitemid, ri.ItemID AS itemid_id, "
            "i.ItemName AS itemname, i.Quantity AS quantity, ri.QtyRequested AS qtyrequested, "
            "ri.QtyIssued AS qtyissued, ri.QtyApproved AS quantity_approved "
            "FROM request_item ri JOIN item i ON i.ItemID = ri.ItemID "
            "WHERE ri.RequestID = %s ORDER BY ri.RequestItemID",
            [req["requestid"]],
        )
        if legacy_approval_requires_review(req):
            legacy_review.append({
                "request_id": req["requestid"],
                "requester": req["requester"].strip(),
                "store_name": req["storename"],
                "items": [{
                    "request_item_id": line["requestitemid"],
                    "item_name": line["itemname"],
                    "quantity_requested": line["qtyrequested"],
                    "legacy_quantity_recorded": line["qtyissued"],
                } for line in lines],
                "message": "This request was approved before separate approval and issue tracking. Verify its physical issue history before changing stock.",
            })
            continue
        item_summaries = []
        for line in lines:
            if line["quantity_approved"] is None:
                continue
            remaining = max(0, line["quantity_approved"] - line["qtyissued"])
            if remaining:
                item_summaries.append({
                    **request_item_summary(line),
                    "quantity_in_stock": line["quantity"],
                })
        if item_summaries:
            results.append({
                "request_id": req["requestid"],
                "request_date": req["requestdate"],
                "requester": req["requester"].strip(),
                "store_name": req["storename"],
                "status": req["statusname"],
                "items": item_summaries,
            })
    return Response({"requests": results, "legacy_review": legacy_review})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reconcile_legacy_request(request, request_id):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response({"error": "Only the Store Manager can reconcile legacy issue records."}, status=status.HTTP_403_FORBIDDEN)
    reason, raw_items = request.data.get("reason"), request.data.get("items")
    if not isinstance(reason, str) or not reason.strip():
        return Response({"error": "Record how the previous issue history was verified."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(raw_items, list) or not raw_items:
        return Response({"error": "Provide the verified approved and previously issued quantities for every item."}, status=status.HTTP_400_BAD_REQUEST)
    submitted = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            return Response({"error": "Each legacy item entry must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        line_id, approved = entry.get("request_item_id"), entry.get("quantity_approved")
        previously_issued = entry.get("quantity_previously_issued")
        if (isinstance(line_id, bool) or not isinstance(line_id, int)
            or isinstance(approved, bool) or not isinstance(approved, int)
            or isinstance(previously_issued, bool) or not isinstance(previously_issued, int)
            or approved < 0 or previously_issued < 0):
            return Response({"error": "Verified quantities must be non-negative whole numbers."}, status=status.HTTP_400_BAD_REQUEST)
        if line_id in submitted:
            return Response({"error": "A request item can appear only once."}, status=status.HTTP_400_BAD_REQUEST)
        submitted[line_id] = (approved, previously_issued)

    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        req = fetch_one(
            "SELECT r.RequestID, r.StatusID, s.StatusName, r.DecidedAt, r.LegacyReviewedAt "
            "FROM `request` r JOIN status s ON s.StatusID = r.StatusID WHERE r.RequestID = %s" + lock_suffix,
            [request_id],
        )
        if req is None:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        if req["StatusName"].lower() not in {"approved", "partially issued", "issued"} or req["DecidedAt"] is not None or req["LegacyReviewedAt"] is not None:
            return Response({"error": "This request is not an unresolved legacy approval."}, status=status.HTTP_409_CONFLICT)
        lines = fetch_all(
            "SELECT RequestItemID, ItemID, QtyRequested FROM request_item WHERE RequestID = %s ORDER BY RequestItemID" + lock_suffix,
            [request_id],
        )
        if set(submitted) != {line["RequestItemID"] for line in lines}:
            return Response({"error": "Submit verified quantities for every item in the request."}, status=status.HTTP_400_BAD_REQUEST)
        for line in lines:
            approved, previously_issued = submitted[line["RequestItemID"]]
            if approved > line["QtyRequested"] or previously_issued > approved:
                return Response({"error": f"Verified quantities for item {line['ItemID']} exceed the request or approved amount."}, status=status.HTTP_400_BAD_REQUEST)
        is_complete = all(submitted[line["RequestItemID"]][1] == submitted[line["RequestItemID"]][0] for line in lines)
        has_issue = any(submitted[line["RequestItemID"]][1] > 0 for line in lines)
        next_status_name = "Issued" if is_complete else "Partially Issued" if has_issue else "Approved"
        next_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", [next_status_name.lower()])
        if next_status is None:
            return Response({"error": f"{next_status_name} status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        for line in lines:
            approved, previously_issued = submitted[line["RequestItemID"]]
            execute("UPDATE request_item SET QtyApproved = %s, QtyIssued = %s WHERE RequestItemID = %s",
                    [approved, previously_issued, line["RequestItemID"]])
        reviewed_at = timezone.now()
        updated = execute(
            "UPDATE `request` SET StatusID = %s, LegacyReviewReason = %s, LegacyReviewedBy = %s, "
            "LegacyReviewedAt = %s, DecidedAt = %s WHERE RequestID = %s AND StatusID = %s "
            "AND DecidedAt IS NULL AND LegacyReviewedAt IS NULL",
            [next_status["StatusID"], reason.strip(), staff.staffid, reviewed_at, reviewed_at, request_id, req["StatusID"]],
        )
        if updated != 1:
            return Response({"error": "Request changed while its legacy history was being reviewed."}, status=status.HTTP_409_CONFLICT)
    return Response({"message": "Legacy quantities were recorded for review; current stock was not changed.", "request_id": request_id, "status": next_status_name})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_request(request, request_id):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response({"error": "Only the Store Manager can issue approved stock."}, status=status.HTTP_403_FORBIDDEN)
    raw_items, comments = request.data.get("items"), request.data.get("comments", "")
    if not isinstance(raw_items, list) or not raw_items:
        return Response({"error": "Enter a quantity to issue for at least one approved item."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(comments, str) or len(comments) > 500:
        return Response({"error": "Issue notes must be text of at most 500 characters."}, status=status.HTTP_400_BAD_REQUEST)
    submitted = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            return Response({"error": "Each issue line must be an object."}, status=status.HTTP_400_BAD_REQUEST)
        line_id, quantity = entry.get("request_item_id"), entry.get("quantity")
        if (isinstance(line_id, bool) or not isinstance(line_id, int)
            or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0):
            return Response({"error": "Each issue line needs an item ID and positive whole-number quantity."}, status=status.HTTP_400_BAD_REQUEST)
        if line_id in submitted:
            return Response({"error": "An item can appear only once in an issue."}, status=status.HTTP_400_BAD_REQUEST)
        submitted[line_id] = quantity

    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        req = fetch_one(
            "SELECT r.RequestID, r.StaffID, r.StatusID, r.DecidedAt, st.OtherNames, st.SurName "
            "FROM `request` r JOIN staff st ON st.StaffID = r.StaffID WHERE r.RequestID = %s" + lock_suffix,
            [request_id],
        )
        if req is None:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        if req["DecidedAt"] is None:
            return Response({"error": "This request has no verified approval. Review legacy requests before issuing."}, status=status.HTTP_409_CONFLICT)
        lines = fetch_all(
            "SELECT ri.RequestItemID, ri.ItemID, ri.QtyApproved, ri.QtyIssued, i.ItemName, i.Quantity "
            "FROM request_item ri JOIN item i ON i.ItemID = ri.ItemID "
            "WHERE ri.RequestID = %s ORDER BY ri.RequestItemID" + lock_suffix,
            [request_id],
        )
        line_by_id = {line["RequestItemID"]: line for line in lines}
        if not set(submitted).issubset(line_by_id):
            return Response({"error": "One or more items do not belong to this request."}, status=status.HTTP_400_BAD_REQUEST)
        for line_id, quantity in submitted.items():
            line = line_by_id[line_id]
            if line["QtyApproved"] is None:
                return Response({"error": "An item in this request has no approved quantity."}, status=status.HTTP_409_CONFLICT)
            remaining = line["QtyApproved"] - line["QtyIssued"]
            if quantity > remaining:
                return Response({"error": f"Issue quantity for {line['ItemName']} exceeds its approved remaining quantity ({remaining})."}, status=status.HTTP_400_BAD_REQUEST)
            if quantity > line["Quantity"]:
                return Response({"error": f"Only {line['Quantity']} {line['ItemName']} are currently in stock; issue a smaller quantity."}, status=status.HTTP_409_CONFLICT)
        for line_id, quantity in submitted.items():
            line = line_by_id[line_id]
            new_stock = line["Quantity"] - quantity
            updated = execute("UPDATE item SET Quantity = %s WHERE ItemID = %s AND Quantity = %s",
                              [new_stock, line["ItemID"], line["Quantity"]])
            if updated != 1:
                return Response({"error": f"Stock for {line['ItemName']} changed while issuing. Reload and retry."}, status=status.HTTP_409_CONFLICT)
            append_item_audit(
                item_id=line["ItemID"],
                item_name=line["ItemName"],
                action="ISSUE",
                field_changed="quantity",
                old_value=line["Quantity"],
                new_value=new_stock,
                comments=f"Request {request_id}; issued to {req['OtherNames']} {req['SurName']}. {comments.strip()}".strip(),
                changed_by_staff_id=staff.staffid,
                request_item_id=line_id,
                quantity_delta=quantity,
            )
            execute("UPDATE request_item SET QtyIssued = QtyIssued + %s WHERE RequestItemID = %s",
                    [quantity, line_id])
            line["QtyIssued"] += quantity
        all_complete = bool(lines) and all(line["QtyApproved"] is not None and line["QtyIssued"] >= line["QtyApproved"] for line in lines)
        next_status_name = "Issued" if all_complete else "Partially Issued"
        next_status = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", [next_status_name.lower()])
        if next_status is None:
            return Response({"error": f"{next_status_name} status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        execute("UPDATE `request` SET StatusID = %s WHERE RequestID = %s", [next_status["StatusID"], request_id])
    return Response({"message": "Stock issued and inventory updated.", "request_id": request_id, "status": next_status_name})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_request(request, request_id):
    staff = request.user.staff_account.staff
    if staff.positionid_id not in APPROVER_POSITION_IDS:
        return Response({"error": "You are not authorized to reject requests."}, status=status.HTTP_403_FORBIDDEN)
    reason = request.data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return Response({"error": "A reason is required when rejecting a request."}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        req = fetch_one(
            "SELECT r.StatusID, s.StatusName, r.DecidedAt, r.LegacyReviewedAt FROM `request` r "
            "JOIN status s ON s.StatusID = r.StatusID WHERE r.RequestID = %s" + lock_suffix,
            [request_id],
        )
        if req is None:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        if req["StatusName"].lower() != "pending":
            return Response({"error": "Only pending requests can be rejected."}, status=status.HTTP_400_BAD_REQUEST)
        if req["DecidedAt"] is not None or req["LegacyReviewedAt"] is not None:
            return Response({"error": "This request already has a recorded decision."}, status=status.HTTP_409_CONFLICT)
        rejected = fetch_one("SELECT StatusID FROM status WHERE LOWER(StatusName) = %s LIMIT 1", ["rejected"])
        if rejected is None:
            return Response({"error": "Rejected status is not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        updated = execute(
            "UPDATE `request` SET StatusID = %s, ApprovedBy = %s, DecisionReason = %s, DecidedAt = %s "
            "WHERE RequestID = %s AND StatusID = %s AND DecidedAt IS NULL AND LegacyReviewedAt IS NULL",
            [rejected["StatusID"], staff.staffid, reason.strip(), timezone.now(), request_id, req["StatusID"]],
        )
        if updated != 1:
            return Response({"error": "Request changed before rejection could be recorded."}, status=status.HTTP_409_CONFLICT)
    return Response({"message": "Request rejected successfully.", "request_id": request_id, "status": "Rejected"})

def purchase_order_summary(order):
    if not isinstance(order, dict):
        raise TypeError("purchase_order_summary expects a SQL row mapping")
    lines = fetch_all(
        "SELECT pi.PurchaseItemID AS line_id, pi.ItemID AS item_id, i.ItemName AS item_name, "
        "pi.Quantity AS quantity_ordered, pi.UnitCost AS unit_cost, "
        "COALESCE((SELECT SUM(receipt_line.Quantity) FROM purchase_item receipt_line "
        "JOIN purchase receipt ON receipt.PurchaseID = receipt_line.PurchaseID "
        "WHERE receipt.ParentPurchaseID = %s AND receipt_line.ItemID = pi.ItemID), 0) AS quantity_received "
        "FROM purchase_item pi JOIN item i ON i.ItemID = pi.ItemID "
        "WHERE pi.PurchaseID = %s ORDER BY pi.PurchaseItemID",
        [order["purchaseid"], order["purchaseid"]],
    )
    return {
        "purchase_order_id": order["purchaseid"],
        "order_number": order["order_number"],
        "store_id": order["storeid_id"],
        "store_name": order["store_name"],
        "supplier_id": order["supplierid_id"],
        "supplier_name": order["supplier_name"],
        "status": order["order_status"],
        "order_date": order["purchasedate"],
        "expected_date": order["expected_date"],
        "notes": order["notes"],
        "rejection_reason": order["rejection_reason"],
        "lines": [{
            "line_id": line["line_id"],
            "item_id": line["item_id"],
            "item_name": line["item_name"],
            "quantity_ordered": line["quantity_ordered"],
            "quantity_received": line["quantity_received"],
            "quantity_remaining": max(0, line["quantity_ordered"] - line["quantity_received"]),
            "unit_cost": str(line["unit_cost"]),
        } for line in lines],
    }


def pending_issue_updates(item_ids):
    if not item_ids:
        return []
    placeholders = ", ".join(["%s"] * len(item_ids))
    rows = fetch_all(
        f"SELECT r.RequestID, {sql_full_name('st.OtherNames', 'st.SurName')} AS Requester, "
        "i.ItemName, (ri.QtyApproved - ri.QtyIssued) AS QuantityRemaining, "
        "i.Quantity AS QuantityInStock FROM request_item ri "
        "JOIN `request` r ON r.RequestID = ri.RequestID JOIN staff st ON st.StaffID = r.StaffID "
        "JOIN item i ON i.ItemID = ri.ItemID WHERE ri.ItemID IN (" + placeholders + ") "
        "AND r.DecidedAt IS NOT NULL AND ri.QtyApproved IS NOT NULL "
        "AND ri.QtyApproved > ri.QtyIssued ORDER BY r.RequestDate, r.RequestID, ri.RequestItemID",
        list(item_ids),
    )
    return [{
        "request_id": row["RequestID"], "requester": row["Requester"].strip(),
        "item_name": row["ItemName"], "quantity_remaining": row["QuantityRemaining"],
        "quantity_in_stock": row["QuantityInStock"],
    } for row in rows]


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def purchase_orders(request):
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        if staff.positionid_id not in (*PURCHASING_POSITION_IDS, *PURCHASE_ORDER_APPROVER_POSITION_IDS):
            return Response(
                {"error": "You are not authorized to view purchase orders."},
                status=status.HTTP_403_FORBIDDEN,
            )
        order_sql = (
            "SELECT p.PurchaseID AS purchaseid, p.OrderNumber AS order_number, "
            "p.StoreID AS storeid_id, st.StoreName AS store_name, "
            "p.SupplierID AS supplierid_id, sup.SupplierName AS supplier_name, "
            "p.OrderStatus AS order_status, p.PurchaseDate AS purchasedate, "
            "p.ExpectedDate AS expected_date, p.Notes AS notes, "
            "p.RejectionReason AS rejection_reason "
            "FROM purchase p JOIN store st ON st.StoreID = p.StoreID "
            "JOIN supplier sup ON sup.SupplierID = p.SupplierID "
            "WHERE p.TransactionType = 'ORDER'"
        )
        order_params = []
        if staff.positionid_id in PURCHASING_POSITION_IDS:
            order_sql += " AND p.StaffID = %s"
            order_params.append(staff.staffid)
        order_sql += " ORDER BY p.PurchaseDate DESC, p.PurchaseID DESC"
        orders = fetch_all(order_sql, order_params)
        return Response({
            "purchase_orders": [
                purchase_order_summary(order)
                for order in orders
            ],
        })

    if staff.positionid_id not in PURCHASING_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager or Procurement Officer can create purchase orders."},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data
    order_number = data.get("order_number")
    store_id = data.get("store_id")
    supplier_id = data.get("supplier_id")
    order_date = data.get("order_date")
    expected_date = data.get("expected_date") or None
    notes = data.get("notes", "")
    raw_lines = data.get("items")

    if not isinstance(order_number, str) or not order_number.strip() or len(order_number.strip()) > 30:
        return Response(
            {"error": "Enter a unique purchase order number of at most 30 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(order_number.strip()) > 20:
        return Response(
            {"error": "Purchase order number cannot exceed 20 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if fetch_one(
        "SELECT PurchaseID FROM purchase WHERE TransactionType = 'ORDER' AND OrderNumber = %s",
        [order_number.strip()],
    ):
        return Response(
            {"error": "That purchase order number already exists."},
            status=status.HTTP_409_CONFLICT,
        )
    if (
        isinstance(store_id, bool) or not isinstance(store_id, int)
        or isinstance(supplier_id, bool) or not isinstance(supplier_id, int)
    ):
        return Response(
            {"error": "Select a valid store and supplier."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(notes, str) or len(notes) > 1000:
        return Response(
            {"error": "Purchase order notes must be text of at most 1000 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        parsed_order_date = date.fromisoformat(order_date)
        parsed_expected_date = (
            date.fromisoformat(expected_date) if expected_date else None
        )
    except (ValueError, TypeError):
        return Response(
            {"error": "Enter valid order dates and select an existing store and supplier."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    store = fetch_one("SELECT StoreID FROM store WHERE StoreID = %s", [store_id])
    supplier = fetch_one("SELECT SupplierID FROM supplier WHERE SupplierID = %s", [supplier_id])
    if store is None or supplier is None:
        return Response(
            {"error": "Enter valid order dates and select an existing store and supplier."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if parsed_expected_date and parsed_expected_date < parsed_order_date:
        return Response(
            {"error": "Expected delivery cannot be before the order date."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(raw_lines, list) or not raw_lines:
        return Response(
            {"error": "Add at least one item to the purchase order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    archived_ids = archived_item_ids()
    seen_items = set()
    validated_lines = []
    for entry in raw_lines:
        if not isinstance(entry, dict):
            return Response(
                {"error": "Each purchase order item must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item_id = entry.get("item_id")
        quantity = entry.get("quantity")
        try:
            unit_cost = Decimal(str(entry.get("unit_cost")))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"error": "Each item needs a valid unit cost."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            isinstance(item_id, bool) or not isinstance(item_id, int)
            or isinstance(quantity, bool) or not isinstance(quantity, int)
            or quantity <= 0 or item_id in seen_items
            or not unit_cost.is_finite() or unit_cost < 0
            or unit_cost.as_tuple().exponent < -2
        ):
            return Response(
                {"error": "Each item needs a unique item ID, positive whole-number quantity and non-negative unit cost with at most two decimals."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if item_id in archived_ids:
            return Response(
                {"error": "Archived items cannot be ordered."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item = fetch_one("SELECT ItemID, StoreID FROM item WHERE ItemID = %s", [item_id])
        if item is None or item["StoreID"] != store_id:
            return Response(
                {"error": "Every ordered item must belong to the selected store."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        seen_items.add(item_id)
        validated_lines.append((item_id, quantity, unit_cost))

    order_total = sum(
        (unit_cost * quantity for _, quantity, unit_cost in validated_lines),
        Decimal("0.000"),
    ).quantize(Decimal("0.001"))
    with transaction.atomic():
        order_id = insert(
            """
            INSERT INTO purchase
                (StoreID, SupplierID, StaffID, InvoiceNumber, OrderNumber,
                 InvoiceDate, PurchaseDate, TotalAmount, TransactionType,
                 OrderStatus, ExpectedDate, Notes, RejectionReason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ORDER', 'Pending', %s, %s, '')
            """,
            [
                store_id, supplier_id, staff.staffid,
                f"PO-{uuid.uuid4().hex[:16]}", order_number.strip(),
                parsed_order_date, parsed_order_date, order_total,
                parsed_expected_date, notes.strip(),
            ],
        )
        current_max = fetch_one(
            "SELECT COALESCE(MAX(PurchaseItemID), 0) AS max_id FROM purchase_item"
        )["max_id"]
        for index, (item_id, quantity, unit_cost) in enumerate(validated_lines, start=1):
            execute(
                "INSERT INTO purchase_item (PurchaseItemID, PurchaseID, ItemID, UnitCost, Quantity) "
                "VALUES (%s, %s, %s, %s, %s)",
                [current_max + index, order_id, item_id, unit_cost, quantity],
            )
    order = fetch_one(
        "SELECT p.PurchaseID AS purchaseid, p.OrderNumber AS order_number, "
        "p.StoreID AS storeid_id, st.StoreName AS store_name, "
        "p.SupplierID AS supplierid_id, sup.SupplierName AS supplier_name, "
        "p.OrderStatus AS order_status, p.PurchaseDate AS purchasedate, "
        "p.ExpectedDate AS expected_date, p.Notes AS notes, p.RejectionReason AS rejection_reason "
        "FROM purchase p JOIN store st ON st.StoreID = p.StoreID "
        "JOIN supplier sup ON sup.SupplierID = p.SupplierID WHERE p.PurchaseID = %s",
        [order_id],
    )

    return Response({
        "message": "Purchase order submitted for approval.",
        "purchase_order": purchase_order_summary(order),
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_purchase_orders(request):
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in PURCHASE_ORDER_APPROVER_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to approve purchase orders."},
            status=status.HTTP_403_FORBIDDEN,
        )
    orders = fetch_all(
        "SELECT p.PurchaseID AS purchaseid, p.OrderNumber AS order_number, "
        "p.StoreID AS storeid_id, st.StoreName AS store_name, "
        "p.SupplierID AS supplierid_id, sup.SupplierName AS supplier_name, "
        "p.OrderStatus AS order_status, p.PurchaseDate AS purchasedate, "
        "p.ExpectedDate AS expected_date, p.Notes AS notes, p.RejectionReason AS rejection_reason "
        "FROM purchase p JOIN store st ON st.StoreID = p.StoreID "
        "JOIN supplier sup ON sup.SupplierID = p.SupplierID "
        "WHERE p.TransactionType = 'ORDER' AND p.OrderStatus = 'Pending' "
        "ORDER BY p.PurchaseDate, p.PurchaseID"
    )
    return Response({"purchase_orders": [purchase_order_summary(order) for order in orders]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decide_purchase_order(request, order_id):
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in PURCHASE_ORDER_APPROVER_POSITION_IDS:
        return Response(
            {"error": "Only the Principal or Deputy Principal can decide purchase orders."},
            status=status.HTTP_403_FORBIDDEN,
        )
    decision = request.data.get("decision")
    reason = request.data.get("reason", "")
    if decision not in {"APPROVED", "REJECTED"}:
        return Response(
            {"error": "Choose APPROVED or REJECTED."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(reason, str) or (
        decision == "REJECTED" and not reason.strip()
    ):
        return Response(
            {"error": "A reason is required when rejecting a purchase order."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        order = fetch_one(
            "SELECT OrderStatus FROM purchase WHERE PurchaseID = %s AND TransactionType = 'ORDER'" + lock_suffix,
            [order_id],
        )
        if order is None:
            return Response(
                {"error": "Purchase order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if order["OrderStatus"] != "Pending":
            return Response(
                {"error": "Only pending purchase orders can be decided."},
                status=status.HTTP_409_CONFLICT,
            )
        next_status = "Approved" if decision == "APPROVED" else "Rejected"
        updated = execute(
            "UPDATE purchase SET ApprovedBy = %s, OrderStatus = %s, RejectionReason = %s "
            "WHERE PurchaseID = %s AND TransactionType = 'ORDER' AND OrderStatus = 'Pending'",
            [staff.staffid, next_status, reason.strip() if decision == "REJECTED" else "", order_id],
        )
        if updated != 1:
            return Response({"error": "Purchase order changed before the decision was saved."}, status=status.HTTP_409_CONFLICT)
    return Response({
        "message": f"Purchase order {next_status.lower()}.",
        "purchase_order_id": order_id,
        "status": next_status,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def receiving_options(request):
    """Return the data needed by the Store Manager's receiving screen."""
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can access goods receiving."},
            status=status.HTTP_403_FORBIDDEN,
        )

    stores = fetch_all("SELECT StoreID AS storeid, StoreName AS storename FROM store ORDER BY StoreID")
    suppliers = fetch_all("SELECT SupplierID AS supplierid, SupplierName AS suppliername FROM supplier ORDER BY SupplierID")
    items = [
        {
            "item_id": item["ItemID"],
            "item_name": item["ItemName"],
            "store_id": item["StoreID"],
            "store_name": item["StoreName"],
            "quantity_in_stock": item["Quantity"],
            "unit_id": item["UnitID"],
        }
        for item in fetch_all(
            "SELECT i.ItemID, i.ItemName, i.StoreID, s.StoreName, i.Quantity, i.UnitID "
            "FROM item i JOIN store s ON s.StoreID = i.StoreID "
            "WHERE COALESCE(i.IsArchived, 0) = 0 ORDER BY i.ItemName"
        )
    ]
    open_orders = [
        purchase_order_summary(order)
        for order in fetch_all(
            "SELECT p.PurchaseID AS purchaseid, p.OrderNumber AS order_number, "
            "p.StoreID AS storeid_id, st.StoreName AS store_name, "
            "p.SupplierID AS supplierid_id, sup.SupplierName AS supplier_name, "
            "p.OrderStatus AS order_status, p.PurchaseDate AS purchasedate, "
            "p.ExpectedDate AS expected_date, p.Notes AS notes, p.RejectionReason AS rejection_reason "
            "FROM purchase p JOIN store st ON st.StoreID = p.StoreID "
            "JOIN supplier sup ON sup.SupplierID = p.SupplierID "
            "WHERE p.TransactionType = 'ORDER' AND p.OrderStatus IN ('Approved', 'Partially Received') "
            "ORDER BY p.PurchaseDate, p.PurchaseID"
        )
    ]

    return Response({
        "stores": stores,
        "suppliers": suppliers,
        "items": items,
        "purchase_orders": open_orders,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def receive_goods(request):
    """Create a purchase and GRN, then increase stock atomically."""
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can receive goods."},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data

    purchase_order_id = data.get("purchase_order_id")
    store_id = data.get("store_id")
    supplier_id = data.get("supplier_id")
    invoice_number = data.get("invoice_number")
    grn_number = data.get("grn_number")
    remarks = data.get("remarks", "")
    raw_items = data.get("items")

    if (
        isinstance(purchase_order_id, bool)
        or not isinstance(purchase_order_id, int)
    ):
        return Response(
            {"error": "Select an approved purchase order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(store_id, bool) or not isinstance(store_id, int):
        return Response(
            {"error": "Select a valid store."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(supplier_id, bool) or not isinstance(supplier_id, int):
        return Response(
            {"error": "Select a valid supplier."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(invoice_number, str) or not invoice_number.strip():
        return Response(
            {"error": "Supplier invoice number is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    invoice_number = invoice_number.strip()

    if len(invoice_number) > 20:
        return Response(
            {"error": "Invoice number cannot exceed 20 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(grn_number, str) or not grn_number.strip():
        return Response(
            {"error": "GRN number is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grn_number = grn_number.strip()

    if len(grn_number) > 50:
        return Response(
            {"error": "GRN number cannot exceed 50 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(remarks, str) or len(remarks) > 255:
        return Response(
            {"error": "Remarks must be text of at most 255 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(raw_items, list) or not raw_items:
        return Response(
            {"error": "Add at least one item to the delivery."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate all dates before opening the transaction.
    parsed_dates = {}

    for field in ("invoice_date", "purchase_date", "grn_date"):
        value = data.get(field)

        try:
            parsed_dates[field] = (
                date.fromisoformat(value)
                if isinstance(value, str)
                else None
            )
        except ValueError:
            parsed_dates[field] = None

        if parsed_dates[field] is None:
            return Response(
                {"error": f"Provide a valid {field.replace('_', ' ')}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if fetch_one("SELECT PurchaseID FROM purchase WHERE InvoiceNumber = %s", [invoice_number]):
        return Response(
            {"error": "That supplier invoice number has already been recorded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if fetch_one("SELECT GRNID FROM grn WHERE GRNNumber = %s", [grn_number]):
        return Response(
            {"error": "That GRN number has already been recorded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    store = fetch_one("SELECT StoreID FROM store WHERE StoreID = %s", [store_id])
    supplier = fetch_one("SELECT SupplierID FROM supplier WHERE SupplierID = %s", [supplier_id])
    if store is None or supplier is None:
        return Response(
            {"error": "The selected store or supplier does not exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    purchase_order = fetch_one(
        "SELECT PurchaseID, StoreID, SupplierID FROM purchase "
        "WHERE PurchaseID = %s AND TransactionType = 'ORDER' "
        "AND OrderStatus IN ('Approved', 'Partially Received')",
        [purchase_order_id],
    )
    if purchase_order is None:
        return Response(
            {"error": "Select an approved purchase order with goods still outstanding."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        purchase_order["StoreID"] != store_id
        or purchase_order["SupplierID"] != supplier_id
    ):
        return Response(
            {"error": "Store and supplier must match the selected purchase order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate every line and calculate the invoice total.
    validated_items = []
    seen_item_ids = set()
    total_amount = Decimal("0.000")

    for entry in raw_items:
        if not isinstance(entry, dict):
            return Response(
                {"error": "Each delivery item must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item_id = entry.get("item_id")
        quantity = entry.get("quantity")
        raw_unit_cost = entry.get("unit_cost")

        if (
            isinstance(item_id, bool)
            or not isinstance(item_id, int)
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return Response(
                {"error": "Each item needs a valid item ID and positive whole-number quantity."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if item_id in seen_item_ids:
            return Response(
                {"error": "An item can appear only once in a delivery. Combine its quantities."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        seen_item_ids.add(item_id)

        try:
            unit_cost = Decimal(str(raw_unit_cost))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"error": "Each item needs a valid unit cost."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not unit_cost.is_finite() or unit_cost < 0:
            return Response(
                {"error": "Unit cost must be a non-negative amount."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if unit_cost.as_tuple().exponent < -2:
            return Response(
                {"error": "Unit cost can have at most two decimal places."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(unit_cost.as_tuple().digits) > 12:
            return Response(
                {"error": "Unit cost is too large."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = fetch_one("SELECT ItemID, ItemName, StoreID FROM item WHERE ItemID = %s", [item_id])
        if item is None:
            return Response(
                {"error": f"Item {item_id} was not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if item["StoreID"] != store_id:
            return Response(
                {
                    "error": (
                        f"{item['ItemName']} does not belong to "
                        f"the selected store."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_line = fetch_one(
            "SELECT Quantity FROM purchase_item WHERE PurchaseID = %s AND ItemID = %s",
            [purchase_order_id, item_id],
        )
        already_received = fetch_one(
            "SELECT COALESCE(SUM(pi.Quantity), 0) AS total FROM purchase_item pi "
            "JOIN purchase p ON p.PurchaseID = pi.PurchaseID "
            "WHERE p.ParentPurchaseID = %s AND pi.ItemID = %s",
            [purchase_order_id, item_id],
        )["total"]
        if (
            order_line is None
            or order_line["Quantity"] - already_received < quantity
        ):
            return Response(
                {"error": f"{item['ItemName']} quantity exceeds the amount remaining on the purchase order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subtotal = (unit_cost * quantity).quantize(Decimal("0.01"))
        total_amount += subtotal

        validated_items.append({
            "item_id": item_id,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "subtotal": subtotal,
        })

    if total_amount > Decimal("999999999.999"):
        return Response(
            {"error": "The purchase total exceeds the database limit."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            if fetch_one("SELECT PurchaseID FROM purchase WHERE InvoiceNumber = %s", [invoice_number]):
                return Response({"error": "That supplier invoice number has already been recorded."}, status=status.HTTP_400_BAD_REQUEST)
            if fetch_one("SELECT GRNID FROM grn WHERE GRNNumber = %s", [grn_number]):
                return Response({"error": "That GRN number has already been recorded."}, status=status.HTTP_400_BAD_REQUEST)

            lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
            locked_order = fetch_one(
                "SELECT PurchaseID, OrderStatus FROM purchase WHERE PurchaseID = %s "
                "AND TransactionType = 'ORDER'" + lock_suffix,
                [purchase_order_id],
            )
            if locked_order is None or locked_order["OrderStatus"] not in {"Approved", "Partially Received"}:
                return Response({"error": "This purchase order is no longer open for receiving."}, status=status.HTTP_409_CONFLICT)

            locked_order_lines = {
                line["ItemID"]: line for line in fetch_all(
                    "SELECT ItemID, Quantity FROM purchase_item WHERE PurchaseID = %s ORDER BY PurchaseItemID" + lock_suffix,
                    [purchase_order_id],
                )
            }
            for entry in validated_items:
                order_line = locked_order_lines.get(entry["item_id"])
                received = fetch_one(
                    "SELECT COALESCE(SUM(pi.Quantity), 0) AS total FROM purchase_item pi "
                    "JOIN purchase p ON p.PurchaseID = pi.PurchaseID "
                    "WHERE p.ParentPurchaseID = %s AND pi.ItemID = %s",
                    [purchase_order_id, entry["item_id"]],
                )["total"]
                if order_line is None or order_line["Quantity"] - received < entry["quantity"]:
                    return Response({"error": "The requested delivery quantity exceeds the remaining purchase order quantity. Refresh and try again."}, status=status.HTTP_409_CONFLICT)

            purchase_id = insert(
                "INSERT INTO purchase (StoreID, SupplierID, StaffID, InvoiceNumber, InvoiceDate, "
                "PurchaseDate, TotalAmount, TransactionType, ParentPurchaseID, OrderStatus, Notes, RejectionReason) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'RECEIPT', %s, '', '', '')",
                [store_id, supplier_id, staff.staffid, invoice_number,
                 parsed_dates["invoice_date"], parsed_dates["purchase_date"],
                 total_amount, purchase_order_id],
            )
            last_line_id = fetch_one("SELECT COALESCE(MAX(PurchaseItemID), 0) AS max_id FROM purchase_item")["max_id"]
            for offset, entry in enumerate(validated_items, start=1):
                execute(
                    "INSERT INTO purchase_item (PurchaseItemID, PurchaseID, ItemID, UnitCost, Quantity) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [last_line_id + offset, purchase_id, entry["item_id"], entry["unit_cost"], entry["quantity"]],
                )
            grn_id = insert(
                "INSERT INTO grn (PurchaseID, GRNNumber, GRNDate, StaffID, Remarks) VALUES (%s, %s, %s, %s, %s)",
                [purchase_id, grn_number, parsed_dates["grn_date"], staff.staffid, remarks.strip()],
            )

            all_received = True
            for item_id, order_line in locked_order_lines.items():
                received = fetch_one(
                    "SELECT COALESCE(SUM(pi.Quantity), 0) AS total FROM purchase_item pi "
                    "JOIN purchase p ON p.PurchaseID = pi.PurchaseID "
                    "WHERE p.ParentPurchaseID = %s AND pi.ItemID = %s",
                    [purchase_order_id, item_id],
                )["total"]
                if received < order_line["Quantity"]:
                    all_received = False
                    break
            purchase_order_status = "Received" if all_received else "Partially Received"
            execute("UPDATE purchase SET OrderStatus = %s WHERE PurchaseID = %s", [purchase_order_status, purchase_order_id])

            for entry in validated_items:
                item = fetch_one(
                    "SELECT ItemName, Quantity FROM item WHERE ItemID = %s" + lock_suffix,
                    [entry["item_id"]],
                )
                if item is None:
                    raise IntegrityError("Received item no longer exists.")
                old_quantity = item["Quantity"]
                new_quantity = old_quantity + entry["quantity"]
                updated = execute(
                    "UPDATE item SET Quantity = %s WHERE ItemID = %s AND Quantity = %s",
                    [new_quantity, entry["item_id"], old_quantity],
                )
                if updated != 1:
                    raise IntegrityError("Item stock changed during receipt.")
                append_item_audit(
                    item_id=entry["item_id"],
                    item_name=item["ItemName"],
                    action="RECEIVE",
                    field_changed="quantity",
                    old_value=old_quantity,
                    new_value=new_quantity,
                    comments=f"GRN {grn_number}; invoice {invoice_number}. {remarks.strip()}".strip(),
                    changed_by_staff_id=staff.staffid,
                    quantity_delta=entry["quantity"],
                )

    except IntegrityError:
        logger.exception("Goods receipt could not be committed because of a database constraint.")
        return Response(
            {
                "error": (
                    "The invoice, GRN, or purchase-line ID conflicted "
                    "with an existing record. No stock changes were saved."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "message": "Goods received successfully.",
            "purchase_id": purchase_id,
            "grn_id": grn_id,
            "grn_number": grn_number,
            "invoice_number": invoice_number,
            "total_amount": str(total_amount),
            "items_received": len(validated_items),
            "purchase_order_status": purchase_order_status,
            "pending_issue_updates": pending_issue_updates(
                {entry["item_id"] for entry in validated_items}
            ),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_dashboard(request):
    staff = request.user.staff_account.staff
    position_id = staff.positionid_id
    if position_id not in INVENTORY_VIEW_POSITION_IDS:
        return Response({"error": "You are not authorized to view management reports."}, status=status.HTTP_403_FORBIDDEN)

    stores = fetch_all("SELECT StoreID AS storeid, StoreName AS storename FROM store ORDER BY StoreID")
    stock_by_store = fetch_all(
        "SELECT i.StoreID AS storeid, s.StoreName AS storeid__storename, "
        "COUNT(i.ItemID) AS item_count, COALESCE(SUM(i.Quantity), 0) AS total_quantity, "
        "SUM(CASE WHEN i.Quantity <= i.ReorderLevel THEN 1 ELSE 0 END) AS low_stock_count "
        "FROM item i JOIN store s ON s.StoreID = i.StoreID GROUP BY i.StoreID, s.StoreName ORDER BY i.StoreID"
    )

    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")
    store_id = request.query_params.get("store_id")
    for key, value in (("from_date", from_date), ("to_date", to_date)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                return Response({"error": f"{key} must use YYYY-MM-DD format."}, status=status.HTTP_400_BAD_REQUEST)
    if from_date and to_date and from_date > to_date:
        return Response({"error": "from_date cannot be after to_date."}, status=status.HTTP_400_BAD_REQUEST)

    audit_sql = "SELECT ItemID, ItemName, StoreID, AuditHistory FROM item"
    audit_filters = []
    audit_params = []
    if store_id:
        try:
            store_id_value = int(store_id)
        except ValueError:
            return Response({"error": "store_id must be a valid store ID."}, status=status.HTTP_400_BAD_REQUEST)
        audit_filters.append("StoreID = %s")
        audit_params.append(store_id_value)
    if audit_filters:
        audit_sql += " WHERE " + " AND ".join(audit_filters)

    stock_movements = []
    for item in fetch_all(audit_sql, audit_params):
        for audit in load_item_audit_history(item["AuditHistory"]):
            if audit.get("field_changed") != "quantity":
                continue
            changed_at = audit.get("changed_at")
            changed_at_text = changed_at.isoformat() if hasattr(changed_at, "isoformat") else str(changed_at)
            movement_date = changed_at_text[:10]
            if from_date and movement_date < from_date:
                continue
            if to_date and movement_date > to_date:
                continue
            try:
                old_quantity = int(audit["old_value"])
                new_quantity = int(audit["new_value"])
            except (KeyError, TypeError, ValueError):
                continue
            stock_movements.append({
                "audit_id": audit["audit_id"],
                "item_id": audit.get("item_id", item["ItemID"]),
                "item_name": audit.get("item_name", item["ItemName"]),
                "action": audit.get("action", "STOCK_ADJUSTMENT"),
                "old_quantity": old_quantity,
                "new_quantity": new_quantity,
                "quantity_change": new_quantity - old_quantity,
                "movement_type": "RECEIVED" if audit.get("action") == "RECEIVE" else "ISSUED" if audit.get("action") == "ISSUE" else "ADJUSTMENT",
                "changed_at": changed_at_text,
                "comments": audit.get("comments", ""),
            })
    stock_movements.sort(key=lambda movement: movement["changed_at"], reverse=True)

    request_statuses = fetch_all(
        "SELECT s.StatusName AS statusname, COUNT(r.RequestID) AS request_count "
        "FROM status s LEFT JOIN `request` r ON r.StatusID = s.StatusID GROUP BY s.StatusID, s.StatusName"
    )
    totals = fetch_one(
        "SELECT COALESCE(SUM(QtyRequested), 0) AS total_requested, "
        "COALESCE(SUM(QtyApproved), 0) AS total_approved, "
        "COALESCE(SUM(QtyIssued), 0) AS total_issued FROM request_item"
    )
    totals["legacy_requests_needing_review"] = fetch_one(
        "SELECT COUNT(*) AS count FROM `request` r JOIN status s ON s.StatusID = r.StatusID "
        "WHERE LOWER(s.StatusName) IN ('approved', 'partially issued', 'issued') "
        "AND r.DecidedAt IS NULL AND r.LegacyReviewedAt IS NULL"
    )["count"]
    request_totals = {
        "total_requested": totals["total_requested"],
        "total_approved": totals["total_approved"],
        "total_issued": totals["total_issued"],
        "legacy_requests_needing_review": totals["legacy_requests_needing_review"],
    }

    month_expression = "DATE_FORMAT(PurchaseDate, '%%Y-%%m-01')" if connection.vendor == "mysql" else "strftime('%Y-%m-01', PurchaseDate)"
    monthly_purchases = fetch_all(
        f"SELECT {month_expression} AS month, COUNT(PurchaseID) AS purchase_count, "
        "SUM(TotalAmount) AS total_amount FROM purchase WHERE TransactionType = 'RECEIPT' "
        "GROUP BY month ORDER BY month"
    )
    supplier_totals = fetch_all(
        "SELECT p.SupplierID AS supplierid, s.SupplierName AS supplierid__suppliername, "
        "COUNT(p.PurchaseID) AS purchase_count, SUM(p.TotalAmount) AS total_amount "
        "FROM purchase p JOIN supplier s ON s.SupplierID = p.SupplierID "
        "WHERE p.TransactionType = 'RECEIPT' GROUP BY p.SupplierID, s.SupplierName ORDER BY total_amount DESC"
    )
    grn_count = fetch_one("SELECT COUNT(*) AS count FROM grn")["count"]
    staff_total = fetch_one("SELECT COUNT(*) AS count FROM staff")["count"]
    staff_by_department = fetch_all(
        "SELECT d.DepartmentID AS departmentid, d.DepartmentName AS departmentname, COUNT(st.StaffID) AS staff_count "
        "FROM department d LEFT JOIN staff st ON st.DepartmentID = d.DepartmentID "
        "GROUP BY d.DepartmentID, d.DepartmentName ORDER BY d.DepartmentID"
    )
    staff_by_position = fetch_all(
        "SELECT p.PositionID AS positionid, p.PositionName AS positionname, COUNT(st.StaffID) AS staff_count "
        "FROM position p LEFT JOIN staff st ON st.PositionID = p.PositionID "
        "GROUP BY p.PositionID, p.PositionName ORDER BY p.PositionID"
    )
    return Response({
        "stores": stores,
        "stock_by_store": stock_by_store,
        "staff_total": staff_total,
        "staff_by_department": staff_by_department,
        "staff_by_position": staff_by_position,
        "request_statuses": request_statuses,
        "request_totals": request_totals,
        "monthly_purchases": [{
            "month": str(row["month"])[:7] if row["month"] else None,
            "purchase_count": row["purchase_count"],
            "total_amount": str(row["total_amount"] or 0),
        } for row in monthly_purchases],
        "supplier_totals": [{
            "supplier_id": row["supplierid"],
            "supplier_name": row["supplierid__suppliername"],
            "purchase_count": row["purchase_count"],
            "total_amount": str(row["total_amount"] or 0),
        } for row in supplier_totals],
        "grn_count": grn_count,
        "stock_movements": stock_movements,
        "movement_filters": {"from_date": from_date, "to_date": to_date, "store_id": store_id},
    })


# ============================================================
# MANAGEMENT: STAFF, INVENTORY ITEMS, AND SUPPLIERS
# ============================================================

from django.db import IntegrityError


MANAGEMENT_POSITIONS = MANAGEMENT_POSITION_IDS
# 5 = Principal, 7 = Store Manager, 8 = Procurement Officer


def get_management_staff(request):
    """Return the logged-in staff member if they have management access."""
    try:
        staff = request.user.staff_account.staff
    except (AttributeError, AttributeError):
        return None

    if staff.positionid_id not in MANAGEMENT_POSITIONS:
        return None

    return staff


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def staff_management(request):
    if get_management_staff(request) is None:
        return Response({"error": "You are not authorized to manage staff."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        staff_members = fetch_all(
            "SELECT s.StaffID AS staff_id, s.SurName AS surname, s.OtherNames AS othernames, "
            "s.DepartmentID AS department_id, d.DepartmentName AS department, "
            "s.PositionID AS position_id, p.PositionName AS position, s.Contact AS contact, "
            "COALESCE(s.Email, '') AS email, "
            "(s.PasswordHash IS NOT NULL AND s.PasswordHash <> '!') AS login_ready "
            "FROM staff s JOIN department d ON d.DepartmentID = s.DepartmentID "
            "JOIN position p ON p.PositionID = s.PositionID ORDER BY s.StaffID"
        )
        departments = fetch_all("SELECT DepartmentID AS departmentid, DepartmentName AS departmentname FROM department ORDER BY DepartmentID")
        positions = fetch_all("SELECT PositionID AS positionid, PositionName AS positionname FROM position ORDER BY PositionID")
        return Response({"staff": staff_members, "departments": departments, "positions": positions})

    data = request.data
    surname = data.get("surname")
    othernames = data.get("othernames")
    contact = data.get("contact")
    email = data.get("email")
    department_id = data.get("department_id")
    position_id = data.get("position_id")
    for field, value in {"surname": surname, "othernames": othernames, "contact": contact}.items():
        if not isinstance(value, str) or not value.strip():
            return Response({"error": f"{field.replace('_', ' ').title()} is required."}, status=status.HTTP_400_BAD_REQUEST)
    if len(surname.strip()) > 50 or len(othernames.strip()) > 100:
        return Response({"error": "Name is too long."}, status=status.HTTP_400_BAD_REQUEST)
    if len(contact.strip()) > 20:
        return Response({"error": "Contact cannot exceed 20 characters."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(email, str) or not email.strip():
        return Response({"error": "A staff email address is required to send the account setup link."}, status=status.HTTP_400_BAD_REQUEST)
    email = email.strip()
    try:
        validate_email(email)
        department_id = int(department_id)
        position_id = int(position_id)
    except (ValidationError, TypeError, ValueError):
        return Response({"error": "Enter a valid email address and select a valid department and position."}, status=status.HTTP_400_BAD_REQUEST)
    if fetch_one("SELECT DepartmentID FROM department WHERE DepartmentID = %s", [department_id]) is None or fetch_one("SELECT PositionID FROM position WHERE PositionID = %s", [position_id]) is None:
        return Response({"error": "Select a valid department and position."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            staff_id = insert(
                "INSERT INTO staff (SurName, OtherNames, DepartmentID, PositionID, Contact, Email, PasswordHash, IsActive) "
                "VALUES (%s, %s, %s, %s, %s, %s, '!', 1)",
                [surname.strip(), othernames.strip(), department_id, position_id, contact.strip(), email],
            )
        send_account_setup_email(staff_id, email)
    except (RuntimeError, OSError, smtplib.SMTPException) as error:
        return Response({"error": f"Staff account could not be created because the setup email was not sent: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except IntegrityError:
        return Response({"error": "The staff member or email already exists."}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"message": "Staff member and login created. A password setup link was emailed.", "staff_id": staff_id}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_staff_setup_email(request, staff_id):
    if get_management_staff(request) is None:
        return Response({"error": "You are not authorized to manage staff accounts."}, status=status.HTTP_403_FORBIDDEN)
    account = fetch_one(
        "SELECT StaffID, Email, PasswordHash FROM staff WHERE StaffID = %s",
        [staff_id],
    )
    if account is None:
        return Response({"error": "No invited login account was found for this staff member."}, status=status.HTTP_404_NOT_FOUND)
    if not account["Email"]:
        return Response({"error": "No email address is recorded for this staff member."}, status=status.HTTP_409_CONFLICT)
    if account["PasswordHash"] and account["PasswordHash"] != "!":
        return Response({"error": "This staff member has already set a password."}, status=status.HTTP_409_CONFLICT)
    try:
        send_account_setup_email(account["StaffID"], account["Email"])
    except (RuntimeError, OSError, smtplib.SMTPException) as error:
        return Response({"error": f"The setup email could not be sent: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"message": f"A new setup link was sent to {account['Email']}."})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def item_management(request):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage inventory items."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        items = fetch_all(
            "SELECT i.ItemID, i.ItemName, i.StoreID, s.StoreName, i.UnitID, "
            "u.UnitName, i.Quantity, i.ReorderLevel, i.IsArchived "
            "FROM item i JOIN store s ON s.StoreID = i.StoreID "
            "JOIN unit u ON u.UnitID = i.UnitID ORDER BY i.ItemID"
        )
        return Response({
            "items": [
                {
                    "item_id": item["ItemID"],
                    "item_name": item["ItemName"],
                    "store_id": item["StoreID"],
                    "store_name": item["StoreName"],
                    "unit_id": item["UnitID"],
                    "unit_name": item["UnitName"],
                    "quantity": item["Quantity"],
                    "reorder_level": item["ReorderLevel"],
                    "is_archived": bool(item["IsArchived"]),
                }
                for item in items
            ],
            "stores": fetch_all("SELECT StoreID AS storeid, StoreName AS storename FROM store ORDER BY StoreID"),
            "units": fetch_all("SELECT UnitID AS unitid, UnitName AS unitname FROM unit ORDER BY UnitID"),
        })

    data = request.data
    item_id = data.get("item_id")
    item_name = data.get("item_name")
    store_id = data.get("store_id")
    unit_id = data.get("unit_id")
    reorder_level = data.get("reorder_level", 0)

    if (
        isinstance(item_id, bool)
        or not isinstance(item_id, int)
        or item_id <= 0
    ):
        return Response(
            {"error": "Enter a positive integer item ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(item_name, str) or not item_name.strip():
        return Response(
            {"error": "Item name is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(item_name.strip()) > 100:
        return Response(
            {"error": "Item name cannot exceed 100 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        isinstance(reorder_level, bool)
        or not isinstance(reorder_level, int)
        or reorder_level < 0
    ):
        return Response(
            {"error": "Reorder level must be a non-negative integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if fetch_one("SELECT ItemID FROM item WHERE ItemID = %s", [item_id]):
        return Response(
            {"error": "That item ID already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        store_id = int(store_id)
        unit_id = int(unit_id)
    except (ValueError, TypeError):
        return Response(
            {"error": "Select a valid store and unit."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if fetch_one("SELECT StoreID FROM store WHERE StoreID = %s", [store_id]) is None or fetch_one("SELECT UnitID FROM unit WHERE UnitID = %s", [unit_id]) is None:
        return Response(
            {"error": "Select a valid store and unit."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        insert(
            "INSERT INTO item (ItemID, ItemName, StoreID, UnitID, Quantity, ReorderLevel, IsArchived) "
            "VALUES (%s, %s, %s, %s, 0, %s, 0)",
            [item_id, item_name.strip(), store_id, unit_id, reorder_level],
        )
    except IntegrityError:
        return Response(
            {"error": "The item could not be created. Check its ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Item created successfully. Record its opening stock through the approved stock-receiving process.",
            "item_id": item_id,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def supplier_management(request):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage suppliers."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        suppliers = fetch_all(
            "SELECT SupplierID AS supplier_id, SupplierName AS supplier_name, "
            "Contact AS contact, Email AS email, Address AS address "
            "FROM supplier ORDER BY SupplierID"
        )
        return Response({"suppliers": suppliers})

    data = request.data
    supplier_id = data.get("supplier_id")
    supplier_name = data.get("supplier_name")
    contact = data.get("contact")
    email = data.get("email", "")
    address = data.get("address")

    if (
        isinstance(supplier_id, bool)
        or not isinstance(supplier_id, int)
        or supplier_id <= 0
    ):
        return Response(
            {"error": "Enter a positive integer supplier ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    for field, value in {
        "supplier_name": supplier_name,
        "contact": contact,
        "address": address,
    }.items():
        if not isinstance(value, str) or not value.strip():
            return Response(
                {"error": f"{field.replace('_', ' ').title()} is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if not isinstance(email, str):
        return Response(
            {"error": "Email must be text."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        len(supplier_name.strip()) > 100
        or len(contact.strip()) > 20
        or len(address.strip()) > 100
        or len(email.strip()) > 100
    ):
        return Response(
            {"error": "One or more supplier fields exceed their maximum length."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if fetch_one("SELECT SupplierID FROM supplier WHERE SupplierID = %s", [supplier_id]):
        return Response(
            {"error": "That supplier ID already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        insert(
            "INSERT INTO supplier (SupplierID, SupplierName, Contact, Email, Address) "
            "VALUES (%s, %s, %s, %s, %s)",
            [supplier_id, supplier_name.strip(), contact.strip(), email.strip() or None, address.strip()],
        )
    except IntegrityError:
        return Response(
            {"error": "The supplier could not be created. Check its ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Supplier created successfully.",
            "supplier_id": supplier_id,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_inventory_item(request, item_id):
    staff = get_management_staff(request)
    if staff is None or staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response({"error": "Only the Principal or Store Manager can delete inventory items."}, status=status.HTTP_403_FORBIDDEN)
    item = fetch_one("SELECT ItemID, Quantity, AuditHistory FROM item WHERE ItemID = %s", [item_id])
    if item is None:
        return Response({"error": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)
    if fetch_one("SELECT RequestItemID FROM request_item WHERE ItemID = %s LIMIT 1", [item_id]):
        return Response({"error": "This item cannot be deleted because it has request history."}, status=status.HTTP_409_CONFLICT)
    if fetch_one("SELECT PurchaseItemID FROM purchase_item WHERE ItemID = %s LIMIT 1", [item_id]):
        return Response({"error": "This item cannot be deleted because it has procurement history."}, status=status.HTTP_409_CONFLICT)
    if load_item_audit_history(item["AuditHistory"]):
        return Response({"error": "This item cannot be deleted because it has audit history."}, status=status.HTTP_409_CONFLICT)
    if item["Quantity"] != 0:
        return Response({"error": "Only items with zero stock can be deleted."}, status=status.HTTP_409_CONFLICT)
    try:
        deleted = execute("DELETE FROM item WHERE ItemID = %s AND Quantity = 0", [item_id])
    except IntegrityError:
        return Response({"error": "This item cannot be deleted because it has linked records."}, status=status.HTTP_409_CONFLICT)
    if deleted != 1:
        return Response({"error": "Item changed before deletion. Reload and try again."}, status=status.HTTP_409_CONFLICT)
    return Response({"message": "Inventory item deleted successfully."}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_item_archive_state(request, item_id):
    staff = get_management_staff(request)
    if staff is None or staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response({"error": "Only the Principal or Store Manager can archive items."}, status=status.HTTP_403_FORBIDDEN)
    action, reason = request.data.get("action"), request.data.get("reason")
    if action not in {"ARCHIVED", "RESTORED"}:
        return Response({"error": "Choose ARCHIVED or RESTORED."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(reason, str) or not reason.strip():
        return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        lock_suffix = " FOR UPDATE" if connection.vendor == "mysql" else ""
        item = fetch_one(
            "SELECT ItemID, ItemName, IsArchived FROM item WHERE ItemID = %s" + lock_suffix,
            [item_id],
        )
        if item is None:
            return Response({"error": "Inventory item not found."}, status=status.HTTP_404_NOT_FOUND)
        old_archived = bool(item["IsArchived"])
        archive = action == "ARCHIVED"
        if archive == old_archived:
            return Response({"error": "The item already has the requested archive state."}, status=status.HTTP_409_CONFLICT)
        if archive:
            request_lines = fetch_all(
                "SELECT ri.QtyApproved, ri.QtyIssued, r.DecidedAt, r.LegacyReviewedAt, "
                "s.StatusName FROM request_item ri JOIN `request` r ON r.RequestID = ri.RequestID "
                "JOIN status s ON s.StatusID = r.StatusID WHERE ri.ItemID = %s",
                [item_id],
            )
            for line in request_lines:
                if legacy_approval_requires_review({
                    "statusname": line["StatusName"],
                    "decided_at": line["DecidedAt"],
                    "legacy_reviewed_at": line["LegacyReviewedAt"],
                }):
                    return Response({"error": "This item has a legacy request awaiting review. Resolve it before archiving."}, status=status.HTTP_409_CONFLICT)
                if line["QtyApproved"] is not None and line["QtyIssued"] < line["QtyApproved"]:
                    return Response({"error": "This item has approved quantities awaiting issue. Complete or resolve them before archiving."}, status=status.HTTP_409_CONFLICT)
        archived_at = timezone.now() if archive else None
        archive_reason = reason.strip() if archive else None
        updated = execute(
            "UPDATE item SET IsArchived = %s, ArchivedBy = %s, ArchivedAt = %s, ArchiveReason = %s "
            "WHERE ItemID = %s AND IsArchived = %s",
            [archive, staff.staffid if archive else None, archived_at, archive_reason, item_id, old_archived],
        )
        if updated != 1:
            return Response({"error": "Item archive state changed before it could be saved."}, status=status.HTTP_409_CONFLICT)
        append_item_audit(
            item_id=item_id,
            item_name=item["ItemName"],
            action=action,
            field_changed="is_archived",
            old_value=old_archived,
            new_value=archive,
            comments=reason.strip(),
            changed_by_staff_id=staff.staffid,
        )
    return Response({
        "message": "Item archived. It is hidden from new requests and receiving." if archive else "Item restored and available for requests and receiving.",
        "item_id": item_id,
        "is_archived": archive,
    })