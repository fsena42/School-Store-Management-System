
from datetime import date

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, Sum
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Request, RequestItem, Status, StaffAccount, Staff, Department, Position,
    Store, Item, Unit, InventoryAudit,
)
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
from django.db.models import Max

from django.db.models import Count
from django.db.models.functions import TruncMonth

from .models import Purchase, PurchaseItem, Grn, Supplier


@api_view(["POST"])
@permission_classes([AllowAny])
def staff_login(request):
    staff_id = request.data.get("staff_id")
    password = request.data.get("password")

    if staff_id is None or not password:
        return Response(
            {"error": "Staff ID and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    username = str(staff_id).strip()

    user = authenticate(
        request=request,
        username=username,
        password=password,
    )

    if user is None or not user.is_active:
        return Response(
            {"error": "Invalid staff ID or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        account = user.staff_account
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this login."},
            status=status.HTTP_403_FORBIDDEN,
        )

    staff = account.staff
    login(request, user)

    return Response({
        "message": "Login successful.",
        "staff": {
            "staff_id": staff.staffid,
            "surname": staff.surname,
            "othernames": staff.othernames,
            "position_id": staff.positionid_id,
            "position": staff.positionid.positionname,
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_request(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
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

    pending_status = Status.objects.filter(
        statusname__iexact="Pending"
    ).first()

    if pending_status is None:
        return Response(
            {"error": "Pending status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = serializer.validated_data

    with transaction.atomic():
        new_request = Request.objects.create(
            storeid_id=data["store_id"],
            staffid=staff,
            requestdate=date.today(),
            statusid=pending_status,
            approvedby=None,
        )

        for item_data in data["items"]:
            RequestItem.objects.create(
                requestid=new_request,
                itemid_id=item_data["item_id"],
                qtyrequested=item_data["quantity"],
                qtyissued=0,
            )

    return Response(
        {
            "message": "Request submitted successfully.",
            "request_id": new_request.requestid,
            "status": "Pending",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_session(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff record linked to this account."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return Response({
        "authenticated": True,
        "staff_id": staff.staffid,
        "name": f"{staff.surname} {staff.othernames}",
        "position": staff.positionid.positionname,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def staff_logout(request):
    logout(request)
    return Response({"message": "Signed out successfully."})


def send_account_setup_email(user, email):
    if not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
        raise RuntimeError(
            "Email delivery is not configured. Set EMAIL_HOST and "
            "DEFAULT_FROM_EMAIL before inviting staff."
        )

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend_url = getattr(settings, "FRONTEND_URL", "http://127.0.0.1:5173")
    setup_url = (
        f"{frontend_url.rstrip('/')}?setup=1&uid={uid}&token={token}"
    )
    send_mail(
        "Set up your school store account",
        (
            "A school store account was created for you. Open this one-time "
            f"link to choose a password: {setup_url}"
        ),
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )


def archived_item_ids():
    return set(
        Item.objects.filter(is_archived=True).values_list("itemid", flat=True)
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def complete_staff_account_setup(request):
    uid = request.data.get("uid")
    token = request.data.get("token")
    password = request.data.get("password")

    if not all(isinstance(value, str) and value for value in (uid, token, password)):
        return Response(
            {"error": "A valid setup link and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user_id = urlsafe_base64_decode(uid).decode()
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except (ValueError, TypeError, UnicodeDecodeError, get_user_model().DoesNotExist):
        return Response(
            {"error": "This account setup link is invalid or expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not default_token_generator.check_token(user, token):
        return Response(
            {"error": "This account setup link is invalid or expired."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(password, user)
    except ValidationError as error:
        return Response(
            {"error": " ".join(error.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(password)
    user.save(update_fields=["password"])
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
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    position_id = staff.positionid_id

    store_ids = REQUESTABLE_STORES_BY_POSITION.get(position_id, ())

    stores = list(
        Store.objects.filter(storeid__in=store_ids)
        .order_by("storeid")
        .values("storeid", "storename")
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
    except StaffAccount.DoesNotExist:
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

    items = Item.objects.select_related(
        "storeid", "unitid"
    ).annotate(
        has_request_history=Exists(
            RequestItem.objects.filter(itemid_id=OuterRef("itemid"))
        ),
        has_procurement_history=Exists(
            PurchaseItem.objects.filter(itemid_id=OuterRef("itemid"))
        ),
        has_audit_history=Exists(
            InventoryAudit.objects.filter(item_id=OuterRef("itemid"))
        ),
    ).order_by("itemid")

    results = []
    archived_ids = archived_item_ids()
    for item in items:
        if item.has_request_history:
            delete_block_reason = (
                "This item cannot be deleted because it has request history."
            )
        elif item.has_procurement_history:
            delete_block_reason = (
                "This item cannot be deleted because it has procurement history."
            )
        elif item.has_audit_history:
            delete_block_reason = (
                "This item cannot be deleted because it has audit history."
            )
        elif item.is_archived:
            delete_block_reason = (
                "Restore this item before deleting it."
            )
        elif item.quantity != 0:
            delete_block_reason = "Only items with zero stock can be deleted."
        else:
            delete_block_reason = None

        results.append({
            "item_id": item.itemid,
            "item_name": item.itemname,
            "store_id": item.storeid_id,
            "store_name": item.storeid.storename,
            "unit_id": item.unitid_id,
            "quantity": item.quantity,
            "reorder_level": item.reorderlevel,
            "is_archived": item.itemid in archived_ids,
            "delete_block_reason": delete_block_reason,
        })

    return Response({
        "staff_id": staff.staffid,
        "items": results,
    })



@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_inventory_item(request, item_id):
    # Resolve the logged-in staff member.
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response(
            {"error": "Only the Principal or Store Manager can edit inventory."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Every edit must include a reason.
    comments = request.data.get("comments")
    if not isinstance(comments, str) or not comments.strip():
        return Response(
            {"error": "A comment explaining the change is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Find the existing item.
    try:
        item = Item.objects.get(itemid=item_id)
    except Item.DoesNotExist:
        return Response(
            {"error": "Inventory item not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Only allow changes to these fields.
    allowed_fields = {
        "item_name": "itemname",
        "quantity": "quantity",
        "reorder_level": "reorderlevel",
    }

    changes = {
        key: request.data[key]
        for key in allowed_fields
        if key in request.data
    }

    if not changes:
        return Response(
            {"error": "Provide at least one field to update."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate the supplied values before changing anything.
    new_values = {}

    for api_field, value in changes.items():
        model_field = allowed_fields[api_field]

        if api_field == "item_name":
            if not isinstance(value, str) or not value.strip():
                return Response(
                    {"error": "Item name must not be empty."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_values[model_field] = value.strip()

        else:
            # Reject booleans, non-integers and negative quantities.
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                return Response(
                    {"error": f"{api_field} must be a non-negative integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            new_values[model_field] = value

    # Save changes and their audit records together.
    from django.db import transaction

    with transaction.atomic():
        for model_field, new_value in new_values.items():
            old_value = getattr(item, model_field)

            if old_value == new_value:
                continue

            if model_field == "itemname":
                audit_field = "item_name"
            elif model_field == "reorderlevel":
                audit_field = "reorder_level"
            else:
                audit_field = model_field

            InventoryAudit.objects.create(
                item_id=item.itemid,
                item_name=item.itemname,
                action=(
                    "STOCK_ADJUSTMENT"
                    if model_field == "quantity"
                    else "EDIT"
                ),
                field_changed=audit_field,
                old_value=str(old_value),
                new_value=str(new_value),
                comments=comments.strip(),
                changed_by=request.user,
            )

            setattr(item, model_field, new_value)

        item.save()

    return Response({
        "message": "Inventory item updated successfully.",
        "item": {
            "item_id": item.itemid,
            "item_name": item.itemname,
            "quantity": item.quantity,
            "reorder_level": item.reorderlevel,
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_requests(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    requests = (
        Request.objects
        .filter(staffid=staff)
        .select_related("storeid", "statusid")
        .order_by("-requestdate", "-requestid")
    )

    results = []

    for req in requests:
        request_items = (
            RequestItem.objects
            .filter(requestid=req)
            .select_related("itemid")
        )

        legacy_decision = legacy_approval_requires_review(req)

        results.append({
            "request_id": req.requestid,
            "store_id": req.storeid_id,
            "store_name": req.storeid.storename,
            "request_date": req.requestdate,
            "status_id": req.statusid_id,
            "status": req.statusid.statusname,
            "decision_reason": req.decision_reason,
            "legacy_review_required": legacy_decision,
            "items": [
                request_item_summary(line, legacy_decision)
                for line in request_items
            ],
        })

    return Response({"requests": results})


def legacy_approval_requires_review(req):
    return (
        req.statusid.statusname.lower()
        in {"approved", "partially issued", "issued"}
        and req.decided_at is None
        and req.legacy_reviewed_at is None
    )


def request_item_summary(line, legacy_review_required=False):
    issued = line.qtyissued
    if legacy_review_required:
        approved = None
        remaining = 0
    else:
        approved = line.quantity_approved or 0
        remaining = max(0, approved - issued)

    return {
        "request_item_id": line.requestitemid,
        "item_id": line.itemid_id,
        "item_name": line.itemid.itemname,
        "quantity_requested": line.qtyrequested,
        "quantity_approved": approved,
        "quantity_issued": issued,
        "quantity_remaining": remaining,
        "legacy_review_required": legacy_review_required,
        "legacy_quantity_recorded": line.qtyissued if legacy_review_required else None,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_request_draft(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
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

    draft_status = Status.objects.filter(
        statusname__iexact="Draft"
    ).first()

    if draft_status is None:
        return Response(
            {"error": "Draft status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = serializer.validated_data

    with transaction.atomic():
        draft = Request.objects.create(
            storeid_id=data["store_id"],
            staffid=staff,
            requestdate=date.today(),
            statusid=draft_status,
            approvedby=None,
        )

        for item_data in data["items"]:
            RequestItem.objects.create(
                requestid=draft,
                itemid_id=item_data["item_id"],
                qtyrequested=item_data["quantity"],
                qtyissued=0,
            )

    return Response(
        {
            "message": "Draft saved successfully.",
            "request_id": draft.requestid,
            "status": "Draft",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def edit_request_draft(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        draft = Request.objects.get(
            requestid=request_id,
            staffid=staff,
        )
    except Request.DoesNotExist:
        return Response(
            {"error": "Draft not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if draft.statusid.statusname.lower() != "draft":
        return Response(
            {"error": "Only drafts can be edited."},
            status=status.HTTP_400_BAD_REQUEST,
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

    data = serializer.validated_data

    with transaction.atomic():
        draft.storeid_id = data["store_id"]
        draft.save(update_fields=["storeid"])

        # Replace draft lines only after all new data is validated.
        RequestItem.objects.filter(requestid=draft).delete()

        for item_data in data["items"]:
            RequestItem.objects.create(
                requestid=draft,
                itemid_id=item_data["item_id"],
                qtyrequested=item_data["quantity"],
                qtyissued=0,
            )

    return Response({
        "message": "Draft updated successfully.",
        "request_id": draft.requestid,
        "status": "Draft",
    })


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_request_draft(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        draft = Request.objects.get(
            requestid=request_id,
            staffid=staff,
        )
    except Request.DoesNotExist:
        return Response(
            {"error": "Draft not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if draft.statusid.statusname.lower() != "draft":
        return Response(
            {"error": "Only drafts can be deleted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        RequestItem.objects.filter(requestid=draft).delete()
        draft.delete()

    return Response(
        {"message": "Draft deleted successfully."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_request_draft(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        draft = Request.objects.get(
            requestid=request_id,
            staffid=staff,
        )
    except Request.DoesNotExist:
        return Response(
            {"error": "Draft not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if draft.statusid.statusname.lower() != "draft":
        return Response(
            {"error": "Only drafts can be submitted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    pending_status = Status.objects.filter(
        statusname__iexact="Pending"
    ).first()

    if pending_status is None:
        return Response(
            {"error": "Pending status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if not RequestItem.objects.filter(requestid=draft).exists():
        return Response(
            {"error": "A request must contain at least one item."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft_lines = list(RequestItem.objects.filter(requestid=draft))
    serializer = RequestSerializer(
        data={
            "store_id": draft.storeid_id,
            "items": [
                {"item_id": line.itemid_id, "quantity": line.qtyrequested}
                for line in draft_lines
            ],
        },
        context={"staff": staff},
    )
    if not serializer.is_valid():
        return Response(
            {"error": "This draft is no longer valid. Update it before submitting.", "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    draft.statusid = pending_status
    draft.save(update_fields=["statusid"])

    return Response({
        "message": "Request submitted successfully.",
        "request_id": draft.requestid,
        "status": "Pending",
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def requestable_items(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    store_ids = REQUESTABLE_STORES_BY_POSITION.get(staff.positionid_id, ())

    archived_ids = archived_item_ids()
    items = (
        Item.objects
        .filter(storeid_id__in=store_ids)
        .exclude(itemid__in=archived_ids)
        .select_related("storeid")
        .order_by("itemid")
    )

    return Response({
        "items": [
            {
                "item_id": item.itemid,
                "item_name": item.itemname,
                "store_id": item.storeid_id,
                "store_name": item.storeid.storename,
            }
            for item in items
        ]
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_requests(request):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
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

    pending_status = Status.objects.filter(
        statusname__iexact="Pending"
    ).first()

    if pending_status is None:
        return Response(
            {"error": "Pending status is not configured."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    pending = (
        Request.objects
        .filter(statusid=pending_status)
        .select_related("staffid", "storeid", "statusid")
        .order_by("requestdate", "requestid")
    )

    results = []

    for req in pending:
        lines = (
            RequestItem.objects
            .filter(requestid=req)
            .select_related("itemid")
            .order_by("requestitemid")
        )

        results.append({
            "request_id": req.requestid,
            "request_date": req.requestdate,
            "staff_id": req.staffid_id,
            "staff_name": (
                f"{req.staffid.othernames} {req.staffid.surname}".strip()
            ),
            "store_id": req.storeid_id,
            "store_name": req.storeid.storename,
            "status": req.statusid.statusname,
            "items": [
                {
                    "request_item_id": line.requestitemid,
                    "item_id": line.itemid_id,
                    "item_name": line.itemid.itemname,
                    "quantity_requested": line.qtyrequested,
                    "quantity_in_stock": line.itemid.quantity,
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
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in (*APPROVER_POSITION_IDS, *ISSUER_POSITION_IDS):
        return Response(
            {"error": "You are not authorized to view request issue progress."},
            status=status.HTTP_403_FORBIDDEN,
        )

    requests = (
        Request.objects.exclude(statusid__statusname__iexact="Draft")
        .select_related("statusid", "staffid", "storeid")
        .order_by("-requestdate", "-requestid")
    )
    results = []
    for req in requests:
        lines = list(
            RequestItem.objects.filter(requestid=req)
            .select_related("itemid")
            .order_by("requestitemid")
        )
        legacy = legacy_approval_requires_review(req)
        results.append({
            "request_id": req.requestid,
            "request_date": req.requestdate,
            "requester": f"{req.staffid.othernames} {req.staffid.surname}".strip(),
            "store_name": req.storeid.storename,
            "status": req.statusid.statusname,
            "decision_reason": req.decision_reason,
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
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in APPROVER_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to approve requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    approved_items = request.data.get("items")
    reason = request.data.get("reason", "")
    if not isinstance(reason, str):
        return Response(
            {"error": "Approval notes must be text."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(approved_items, list) or not approved_items:
        return Response(
            {"error": "Provide the approved quantity for each requested item."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        try:
            req = (
                Request.objects.select_for_update()
                .select_related("statusid")
                .get(requestid=request_id)
            )
        except Request.DoesNotExist:
            return Response(
                {"error": "Request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if req.statusid.statusname.lower() != "pending":
            return Response(
                {"error": "Only pending requests can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if req.decided_at is not None or req.legacy_reviewed_at is not None:
            return Response(
                {"error": "This request already has a recorded decision."},
                status=status.HTTP_409_CONFLICT,
            )

        lines = list(
            RequestItem.objects.select_for_update()
            .filter(requestid=req)
            .order_by("requestitemid")
        )

        if not lines:
            return Response(
                {"error": "This request has no items."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        submitted = {}

        for entry in approved_items:
            if not isinstance(entry, dict):
                return Response(
                    {"error": "Invalid item quantity data."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item_id = entry.get("request_item_id")
            quantity = entry.get("quantity_approved")

            if (
                isinstance(item_id, bool)
                or not isinstance(item_id, int)
                or isinstance(quantity, bool)
                or not isinstance(quantity, int)
            ):
                return Response(
                    {"error": "Item IDs and quantities must be integers."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if item_id in submitted:
                return Response(
                    {"error": "Duplicate request item."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            submitted[item_id] = quantity

        expected_ids = {line.requestitemid for line in lines}

        if set(submitted) != expected_ids:
            return Response(
                {"error": "Submit an approved quantity for every item in this request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not any(submitted.get(line.requestitemid, 0) > 0 for line in lines):
            return Response(
                {"error": "Approve at least one item quantity, or reject the request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        approved_status_name = "Approved"
        new_status = Status.objects.filter(
            statusname__iexact=approved_status_name
        ).first()
        if new_status is None:
            return Response(
                {"error": "Approved status is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        for line in lines:
            quantity = submitted[line.requestitemid]

            if quantity < 0 or quantity > line.qtyrequested:
                return Response(
                    {
                        "error": (
                            f"Approved quantity for item "
                            f"{line.itemid_id} must be between 0 "
                            f"and {line.qtyrequested}."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        for line in lines:
            line.quantity_approved = submitted[line.requestitemid]
            line.save(update_fields=["quantity_approved"])
        req.statusid = new_status
        req.approvedby = staff
        req.decision_reason = reason.strip()
        req.decided_at = timezone.now()
        req.save(update_fields=[
            "statusid", "approvedby", "decision_reason", "decided_at"
        ])

    return Response({
        "message": "Request quantities approved. The Store Manager must issue stock separately.",
        "request_id": req.requestid,
        "status": approved_status_name,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_issues(request):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can issue approved stock."},
            status=status.HTTP_403_FORBIDDEN,
        )

    request_statuses = Status.objects.filter(
        statusname__in=["Approved", "Partially Issued"]
    )
    pending = (
        Request.objects.filter(statusid__in=request_statuses)
        .select_related("staffid", "storeid", "statusid")
        .order_by("requestdate", "requestid")
    )
    results = []
    legacy_review = []

    for req in pending:
        lines = list(
            RequestItem.objects.filter(requestid=req)
            .select_related("itemid")
            .order_by("requestitemid")
        )

        if legacy_approval_requires_review(req):
            legacy_review.append({
                "request_id": req.requestid,
                "requester": f"{req.staffid.othernames} {req.staffid.surname}".strip(),
                "store_name": req.storeid.storename,
                "items": [
                    {
                        "request_item_id": line.requestitemid,
                        "item_name": line.itemid.itemname,
                        "quantity_requested": line.qtyrequested,
                        "legacy_quantity_recorded": line.qtyissued,
                    }
                    for line in lines
                ],
                "message": (
                    "This request was approved before separate approval "
                    "and issue tracking. Verify its physical issue history "
                    "before changing stock."
                ),
            })
            continue

        item_summaries = []
        for line in lines:
            if line.quantity_approved is None:
                continue
            remaining = max(0, line.quantity_approved - line.qtyissued)
            if remaining:
                item_summaries.append({
                    **request_item_summary(line),
                    "quantity_in_stock": line.itemid.quantity,
                })

        if item_summaries:
            results.append({
                "request_id": req.requestid,
                "request_date": req.requestdate,
                "requester": f"{req.staffid.othernames} {req.staffid.surname}".strip(),
                "store_name": req.storeid.storename,
                "status": req.statusid.statusname,
                "items": item_summaries,
            })

    return Response({
        "requests": results,
        "legacy_review": legacy_review,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reconcile_legacy_request(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can reconcile legacy issue records."},
            status=status.HTTP_403_FORBIDDEN,
        )
    reason = request.data.get("reason")
    raw_items = request.data.get("items")
    if not isinstance(reason, str) or not reason.strip():
        return Response(
            {"error": "Record how the previous issue history was verified."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(raw_items, list) or not raw_items:
        return Response(
            {"error": "Provide the verified approved and previously issued quantities for every item."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    submitted = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            return Response(
                {"error": "Each legacy item entry must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        line_id = entry.get("request_item_id")
        approved = entry.get("quantity_approved")
        previously_issued = entry.get("quantity_previously_issued")
        if (
            isinstance(line_id, bool) or not isinstance(line_id, int)
            or isinstance(approved, bool) or not isinstance(approved, int)
            or isinstance(previously_issued, bool)
            or not isinstance(previously_issued, int)
            or approved < 0 or previously_issued < 0
        ):
            return Response(
                {"error": "Verified quantities must be non-negative whole numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if line_id in submitted:
            return Response(
                {"error": "A request item can appear only once."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        submitted[line_id] = (approved, previously_issued)

    with transaction.atomic():
        try:
            req = Request.objects.select_for_update().get(requestid=request_id)
        except Request.DoesNotExist:
            return Response(
                {"error": "Request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if req.statusid.statusname.lower() not in {
            "approved", "partially issued", "issued"
        } or req.decided_at is not None or req.legacy_reviewed_at is not None:
            return Response(
                {"error": "This request is not an unresolved legacy approval."},
                status=status.HTTP_409_CONFLICT,
            )
        lines = list(
            RequestItem.objects.select_for_update()
            .filter(requestid=req)
            .order_by("requestitemid")
        )
        if set(submitted) != {line.requestitemid for line in lines}:
            return Response(
                {"error": "Submit verified quantities for every item in the request."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for line in lines:
            approved, previously_issued = submitted[line.requestitemid]
            if approved > line.qtyrequested or previously_issued > approved:
                return Response(
                    {"error": f"Verified quantities for item {line.itemid_id} exceed the request or approved amount."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        is_complete = all(
            submitted[line.requestitemid][1] == submitted[line.requestitemid][0]
            for line in lines
        )
        has_issue = any(
            submitted[line.requestitemid][1] > 0
            for line in lines
        )
        next_status_name = (
            "Issued" if is_complete
            else "Partially Issued" if has_issue
            else "Approved"
        )
        next_status = Status.objects.filter(
            statusname__iexact=next_status_name
        ).first()
        if next_status is None:
            return Response(
                {"error": f"{next_status_name} status is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        for line in lines:
            approved, previously_issued = submitted[line.requestitemid]
            line.quantity_approved = approved
            line.qtyissued = previously_issued
            line.save(update_fields=["quantity_approved", "qtyissued"])

        req.statusid = next_status
        req.legacy_review_reason = reason.strip()
        req.legacy_reviewed_by_id = staff.staffid
        req.legacy_reviewed_at = timezone.now()
        req.decided_at = timezone.now()
        req.save(update_fields=[
            "statusid",
            "legacy_review_reason",
            "legacy_reviewed_by_id",
            "legacy_reviewed_at",
            "decided_at",
        ])

    return Response({
        "message": "Legacy quantities were recorded for review; current stock was not changed.",
        "request_id": req.requestid,
        "status": req.statusid.statusname,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def issue_request(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can issue approved stock."},
            status=status.HTTP_403_FORBIDDEN,
        )

    raw_items = request.data.get("items")
    comments = request.data.get("comments", "")
    if not isinstance(raw_items, list) or not raw_items:
        return Response(
            {"error": "Enter a quantity to issue for at least one approved item."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(comments, str) or len(comments) > 500:
        return Response(
            {"error": "Issue notes must be text of at most 500 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    submitted = {}
    for entry in raw_items:
        if not isinstance(entry, dict):
            return Response(
                {"error": "Each issue line must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        line_id = entry.get("request_item_id")
        quantity = entry.get("quantity")
        if (
            isinstance(line_id, bool)
            or not isinstance(line_id, int)
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return Response(
                {"error": "Each issue line needs an item ID and positive whole-number quantity."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if line_id in submitted:
            return Response(
                {"error": "An item can appear only once in an issue."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        submitted[line_id] = quantity

    with transaction.atomic():
        try:
            req = (
                Request.objects.select_for_update()
                .select_related("statusid")
                .get(requestid=request_id)
            )
        except Request.DoesNotExist:
            return Response(
                {"error": "Request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if req.decided_at is None:
            return Response(
                {"error": "This request has no verified approval. Review legacy requests before issuing."},
                status=status.HTTP_409_CONFLICT,
            )

        lines = list(
            RequestItem.objects.select_for_update()
            .filter(requestid=req)
            .select_related("itemid")
            .order_by("requestitemid")
        )
        line_by_id = {line.requestitemid: line for line in lines}
        if not set(submitted).issubset(line_by_id):
            return Response(
                {"error": "One or more items do not belong to this request."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue_rows = []
        for line_id, quantity in submitted.items():
            line = line_by_id[line_id]
            if line.quantity_approved is None:
                return Response(
                    {"error": "An item in this request has no approved quantity."},
                    status=status.HTTP_409_CONFLICT,
                )
            issued_before = line.qtyissued
            remaining = line.quantity_approved - issued_before
            if quantity > remaining:
                return Response(
                    {"error": f"Issue quantity for {line.itemid.itemname} exceeds its approved remaining quantity ({remaining})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item = Item.objects.select_for_update().get(itemid=line.itemid_id)
            if quantity > item.quantity:
                return Response(
                    {"error": f"Only {item.quantity} {line.itemid.itemname} are currently in stock; issue a smaller quantity."},
                    status=status.HTTP_409_CONFLICT,
                )
            issue_rows.append((line, item, quantity, issued_before))

        for line, item, quantity, issued_before in issue_rows:
            old_stock = item.quantity
            new_stock = old_stock - quantity
            item.quantity = new_stock
            item.save(update_fields=["quantity"])
            InventoryAudit.objects.create(
                item_id=item.itemid,
                item_name=item.itemname,
                action="ISSUE",
                field_changed="quantity",
                old_value=str(old_stock),
                new_value=str(new_stock),
                comments=(
                    f"Request {req.requestid}; issued to "
                    f"{req.staffid.othernames} {req.staffid.surname}. "
                    f"{comments.strip()}"
                ).strip(),
                changed_by=request.user,
                changed_by_staff_id=staff.staffid,
                request_item_id=line.requestitemid,
                quantity_delta=quantity,
            )
            line.qtyissued = issued_before + quantity
            line.save(update_fields=["qtyissued"])

        all_complete = bool(lines) and all(
            line.quantity_approved is not None
            and line.qtyissued >= line.quantity_approved
            for line in lines
        )
        next_status_name = "Issued" if all_complete else "Partially Issued"
        next_status = Status.objects.filter(
            statusname__iexact=next_status_name
        ).first()
        if next_status is None:
            return Response(
                {"error": f"{next_status_name} status is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        req.statusid = next_status
        req.save(update_fields=["statusid"])

    return Response({
        "message": "Stock issued and inventory updated.",
        "request_id": req.requestid,
        "status": next_status_name,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_request(request, request_id):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in APPROVER_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to reject requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    reason = request.data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return Response(
            {"error": "A reason is required when rejecting a request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        try:
            req = Request.objects.select_for_update().get(
                requestid=request_id
            )
        except Request.DoesNotExist:
            return Response(
                {"error": "Request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if req.statusid.statusname.lower() != "pending":
            return Response(
                {"error": "Only pending requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if req.decided_at is not None or req.legacy_reviewed_at is not None:
            return Response(
                {"error": "This request already has a recorded decision."},
                status=status.HTTP_409_CONFLICT,
            )

        rejected_status = Status.objects.filter(
            statusname__iexact="Rejected"
        ).first()

        if rejected_status is None:
            return Response(
                {"error": "Rejected status is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        req.statusid = rejected_status
        req.approvedby = staff
        req.decision_reason = reason.strip()
        req.decided_at = timezone.now()
        req.save(update_fields=[
            "statusid", "approvedby", "decision_reason", "decided_at"
        ])

    return Response({
        "message": "Request rejected successfully.",
        "request_id": req.requestid,
        "status": "Rejected",
    })


def purchase_order_summary(order):
    supplier = Supplier.objects.filter(
        supplierid=order.supplierid_id
    ).first()
    store = Store.objects.filter(storeid=order.storeid_id).first()
    lines = []
    for line in PurchaseItem.objects.filter(
        purchaseid_id=order.purchaseid
    ).order_by("purchaseitemid"):
        received = PurchaseItem.objects.filter(
            purchaseid__parent_purchase_id=order.purchaseid,
            itemid_id=line.itemid_id,
        ).aggregate(total=Sum("quantity"))["total"] or 0
        item = Item.objects.filter(itemid=line.itemid_id).first()
        lines.append({
            "line_id": line.purchaseitemid,
            "item_id": line.itemid_id,
            "item_name": item.itemname if item else "Unknown item",
            "quantity_ordered": line.quantity,
            "quantity_received": received,
            "quantity_remaining": max(
                0, line.quantity - received
            ),
            "unit_cost": str(line.unitcost),
        })
    return {
        "purchase_order_id": order.purchaseid,
        "order_number": order.order_number,
        "store_id": order.storeid_id,
        "store_name": store.storename if store else "Unknown store",
        "supplier_id": order.supplierid_id,
        "supplier_name": supplier.suppliername if supplier else "Unknown supplier",
        "status": order.order_status,
        "order_date": order.purchasedate,
        "expected_date": order.expected_date,
        "notes": order.notes,
        "rejection_reason": order.rejection_reason,
        "lines": lines,
    }


def pending_issue_updates(item_ids):
    if not item_ids:
        return []
    updated = []
    lines = (
        RequestItem.objects.filter(itemid_id__in=item_ids)
        .select_related("requestid", "requestid__staffid", "itemid", "requestid__statusid")
        .order_by("requestid__requestdate", "requestid_id", "requestitemid")
    )
    for line in lines:
        if line.requestid.decided_at is None or line.quantity_approved is None:
            continue
        remaining = max(0, line.quantity_approved - line.qtyissued)
        if remaining:
            updated.append({
                "request_id": line.requestid_id,
                "requester": (
                    f"{line.requestid.staffid.othernames} "
                    f"{line.requestid.staffid.surname}"
                ).strip(),
                "item_name": line.itemid.itemname,
                "quantity_remaining": remaining,
                "quantity_in_stock": line.itemid.quantity,
            })
    return updated


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def purchase_orders(request):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
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
        orders = Purchase.objects.filter(
            transaction_type=Purchase.TYPE_ORDER
        )
        if staff.positionid_id in PURCHASING_POSITION_IDS:
            orders = orders.filter(staffid_id=staff.staffid)
        return Response({
            "purchase_orders": [
                purchase_order_summary(order)
                for order in orders.order_by("-purchasedate", "-purchaseid")
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
    if Purchase.objects.filter(
        transaction_type=Purchase.TYPE_ORDER,
        order_number=order_number.strip(),
    ).exists():
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
        store = Store.objects.get(storeid=store_id)
        supplier = Supplier.objects.get(supplierid=supplier_id)
    except (ValueError, TypeError, Store.DoesNotExist, Supplier.DoesNotExist):
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
        item = Item.objects.filter(itemid=item_id).first()
        if item is None or item.storeid_id != store.storeid:
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
        order = Purchase.objects.create(
            storeid=store,
            supplierid=supplier,
            staffid=staff,
            invoicenumber=f"PO-{uuid.uuid4().hex[:16]}",
            order_number=order_number.strip(),
            invoicedate=parsed_order_date,
            purchasedate=parsed_order_date,
            totalamount=order_total,
            transaction_type=Purchase.TYPE_ORDER,
            order_status=Purchase.STATUS_PENDING,
            expected_date=parsed_expected_date,
            notes=notes.strip(),
        )
        last_line_id = PurchaseItem.objects.aggregate(
            max_id=Max("purchaseitemid")
        )["max_id"] or 0
        PurchaseItem.objects.bulk_create([
            PurchaseItem(
                purchaseitemid=last_line_id + index,
                purchaseid=order,
                itemid_id=item_id,
                quantity=quantity,
                unitcost=unit_cost,
            )
            for index, (item_id, quantity, unit_cost) in enumerate(
                validated_lines, start=1
            )
        ])

    return Response({
        "message": "Purchase order submitted for approval.",
        "purchase_order": purchase_order_summary(order),
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pending_purchase_orders(request):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if staff.positionid_id not in PURCHASE_ORDER_APPROVER_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to approve purchase orders."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response({
        "purchase_orders": [
            purchase_order_summary(order)
            for order in Purchase.objects.filter(
                transaction_type=Purchase.TYPE_ORDER,
                order_status=Purchase.STATUS_PENDING,
            ).order_by("purchasedate", "purchaseid")
        ],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def decide_purchase_order(request, order_id):
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
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
        try:
            order = Purchase.objects.select_for_update().get(
                purchaseid=order_id,
                transaction_type=Purchase.TYPE_ORDER,
            )
        except Purchase.DoesNotExist:
            return Response(
                {"error": "Purchase order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if order.order_status != Purchase.STATUS_PENDING:
            return Response(
                {"error": "Only pending purchase orders can be decided."},
                status=status.HTTP_409_CONFLICT,
            )
        order.approved_by_staff_id = staff.staffid
        order.order_status = (
            Purchase.STATUS_APPROVED
            if decision == "APPROVED"
            else Purchase.STATUS_REJECTED
        )
        order.rejection_reason = (
            reason.strip() if decision == "REJECTED" else ""
        )
        order.save(update_fields=[
            "approved_by_staff_id", "order_status", "rejection_reason"
        ])
    return Response({
        "message": f"Purchase order {order.order_status.lower()}.",
        "purchase_order_id": order.purchaseid,
        "status": order.order_status,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def receiving_options(request):
    """Return the data needed by the Store Manager's receiving screen."""
    try:
        staff = request.user.staff_account.staff
    except (StaffAccount.DoesNotExist, AttributeError):
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if staff.positionid_id not in ISSUER_POSITION_IDS:
        return Response(
            {"error": "Only the Store Manager can access goods receiving."},
            status=status.HTTP_403_FORBIDDEN,
        )

    stores = list(
        Store.objects.order_by("storeid").values(
            "storeid", "storename"
        )
    )

    suppliers = list(
        Supplier.objects.order_by("supplierid").values(
            "supplierid", "suppliername"
        )
    )

    archived_ids = archived_item_ids()
    items = [
        {
            "item_id": item.itemid,
            "item_name": item.itemname,
            "store_id": item.storeid_id,
            "store_name": item.storeid.storename,
            "quantity_in_stock": item.quantity,
            "unit_id": item.unitid_id,
        }
        for item in Item.objects.exclude(itemid__in=archived_ids).select_related(
            "storeid", "unitid"
        ).order_by("itemname")
    ]
    open_orders = [
        purchase_order_summary(order)
        for order in Purchase.objects.filter(
            transaction_type=Purchase.TYPE_ORDER,
            order_status__in=[
                Purchase.STATUS_APPROVED,
                Purchase.STATUS_PARTIALLY_RECEIVED,
            ]
        ).order_by("purchasedate", "purchaseid")
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
    except (StaffAccount.DoesNotExist, AttributeError):
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

    if Purchase.objects.filter(invoicenumber=invoice_number).exists():
        return Response(
            {"error": "That supplier invoice number has already been recorded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Grn.objects.filter(grnnumber=grn_number).exists():
        return Response(
            {"error": "That GRN number has already been recorded."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        store = Store.objects.get(storeid=store_id)
        supplier = Supplier.objects.get(supplierid=supplier_id)
        purchase_order = Purchase.objects.get(
            purchaseid=purchase_order_id,
            transaction_type=Purchase.TYPE_ORDER,
            order_status__in=[
                Purchase.STATUS_APPROVED,
                Purchase.STATUS_PARTIALLY_RECEIVED,
            ],
        )
    except (Store.DoesNotExist, Supplier.DoesNotExist):
        return Response(
            {"error": "The selected store or supplier does not exist."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Purchase.DoesNotExist:
        return Response(
            {"error": "Select an approved purchase order with goods still outstanding."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
        purchase_order.storeid_id != store.storeid
        or purchase_order.supplierid_id != supplier.supplierid
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

        try:
            item = Item.objects.get(itemid=item_id)
        except Item.DoesNotExist:
            return Response(
                {"error": f"Item {item_id} was not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if item.storeid_id != store.storeid:
            return Response(
                {
                    "error": (
                        f"{item.itemname} does not belong to "
                        f"the selected store."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_line = PurchaseItem.objects.filter(
            purchaseid=purchase_order,
            itemid_id=item_id,
        ).first()
        already_received = PurchaseItem.objects.filter(
            purchaseid__parent_purchase_id=purchase_order.purchaseid,
            itemid_id=item_id,
        ).aggregate(total=Sum("quantity"))["total"] or 0
        if (
            order_line is None
            or order_line.quantity - already_received < quantity
        ):
            return Response(
                {"error": f"{item.itemname} quantity exceeds the amount remaining on the purchase order."},
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
            # Recheck unique document numbers inside the transaction.
            if Purchase.objects.filter(invoicenumber=invoice_number).exists():
                return Response(
                    {"error": "That supplier invoice number has already been recorded."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if Grn.objects.filter(grnnumber=grn_number).exists():
                return Response(
                    {"error": "That GRN number has already been recorded."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            locked_order = Purchase.objects.select_for_update().get(
                purchaseid=purchase_order.purchaseid,
                transaction_type=Purchase.TYPE_ORDER,
            )
            if locked_order.order_status not in {
                Purchase.STATUS_APPROVED,
                Purchase.STATUS_PARTIALLY_RECEIVED,
            }:
                return Response(
                    {"error": "This purchase order is no longer open for receiving."},
                    status=status.HTTP_409_CONFLICT,
                )
            locked_order_lines = {
                line.itemid_id: line
                for line in PurchaseItem.objects.select_for_update().filter(
                    purchaseid=locked_order
                )
            }
            for entry in validated_items:
                order_line = locked_order_lines.get(entry["item_id"])
                already_received = PurchaseItem.objects.filter(
                    purchaseid__parent_purchase_id=locked_order.purchaseid,
                    itemid_id=entry["item_id"],
                ).aggregate(total=Sum("quantity"))["total"] or 0
                if (
                    order_line is None
                    or order_line.quantity - already_received < entry["quantity"]
                ):
                    return Response(
                        {"error": "The requested delivery quantity exceeds the remaining purchase order quantity. Refresh and try again."},
                        status=status.HTTP_409_CONFLICT,
                    )

            purchase = Purchase.objects.create(
                storeid=store,
                supplierid=supplier,
                staffid=staff,
                invoicenumber=invoice_number,
                invoicedate=parsed_dates["invoice_date"],
                purchasedate=parsed_dates["purchase_date"],
                totalamount=total_amount,
                transaction_type=Purchase.TYPE_RECEIPT,
                parent_purchase=locked_order,
            )

            # PurchaseItemID is the primary key in the existing table.
            last_line = PurchaseItem.objects.aggregate(
                max_id=Max("purchaseitemid")
            )["max_id"] or 0

            for offset, entry in enumerate(validated_items, start=1):
                PurchaseItem.objects.create(
                    purchaseitemid=last_line + offset,
                    purchaseid=purchase,
                    itemid_id=entry["item_id"],
                    quantity=entry["quantity"],
                    unitcost=entry["unit_cost"],
                )

            grn = Grn.objects.create(
                purchaseid=purchase,
                grnnumber=grn_number,
                grndate=parsed_dates["grn_date"],
                staffid=staff,
                remarks=remarks.strip(),
            )
            all_order_lines = list(locked_order_lines.values())
            all_received = all(
                (PurchaseItem.objects.filter(
                    purchaseid__parent_purchase_id=locked_order.purchaseid,
                    itemid_id=line.itemid_id,
                ).aggregate(total=Sum("quantity"))["total"] or 0)
                >= line.quantity
                for line in all_order_lines
            )
            if all_received:
                locked_order.order_status = Purchase.STATUS_RECEIVED
            else:
                locked_order.order_status = Purchase.STATUS_PARTIALLY_RECEIVED
            locked_order.save(update_fields=["order_status"])

            # Lock each stock row and audit every stock increase.
            for entry in validated_items:
                item = Item.objects.select_for_update().get(
                    itemid=entry["item_id"]
                )

                old_quantity = item.quantity
                new_quantity = old_quantity + entry["quantity"]

                item.quantity = new_quantity
                item.save(update_fields=["quantity"])

                InventoryAudit.objects.create(
                    item_id=item.itemid,
                    item_name=item.itemname,
                    action="RECEIVE",
                    field_changed="quantity",
                    old_value=str(old_quantity),
                    new_value=str(new_quantity),
                    comments=(
                        f"GRN {grn.grnnumber}; "
                        f"invoice {purchase.invoicenumber}. "
                        f"{remarks.strip()}"
                    ).strip(),
                    changed_by=request.user,
                    changed_by_staff_id=staff.staffid,
                )

    except IntegrityError:
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
            "purchase_id": purchase.purchaseid,
            "grn_id": grn.grnid,
            "grn_number": grn.grnnumber,
            "invoice_number": purchase.invoicenumber,
            "total_amount": str(purchase.totalamount),
            "items_received": len(validated_items),
            "purchase_order_status": locked_order.order_status,
            "pending_issue_updates": pending_issue_updates(
                {entry["item_id"] for entry in validated_items}
            ),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_dashboard(request):
    try:
        staff = request.user.staff_account.staff
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No staff account is linked to this user."},
            status=status.HTTP_403_FORBIDDEN,
        )

    position_id = staff.positionid_id

    # Management reports are restricted to authorized positions.
    if position_id not in INVENTORY_VIEW_POSITION_IDS:
        return Response(
            {"error": "You are not authorized to view management reports."},
            status=status.HTTP_403_FORBIDDEN,
        )

    stores = list(
        Store.objects.order_by("storeid").values(
            "storeid", "storename"
        )
    )

    stock_by_store = list(
        Item.objects.values(
            "storeid", "storeid__storename"
        ).annotate(
            item_count=Count("itemid"),
            total_quantity=Sum("quantity"),
            low_stock_count=Count(
                "itemid",
                filter=__import__(
                    "django.db.models", fromlist=["Q"]
                ).Q(quantity__lte=__import__(
                    "django.db.models", fromlist=["F"]
                ).F("reorderlevel")),
            ),
        ).order_by("storeid")
    )

    # Optional inventory report filters
    from_date = request.query_params.get("from_date")
    to_date = request.query_params.get("to_date")
    store_id = request.query_params.get("store_id")

    audit_queryset = InventoryAudit.objects.filter(
        field_changed="quantity"
    ).order_by("-changed_at")

    if from_date:
        try:
            date.fromisoformat(from_date)
        except ValueError:
            return Response(
                {"error": "from_date must use YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit_queryset = audit_queryset.filter(
            changed_at__date__gte=from_date
        )

    if to_date:
        try:
            date.fromisoformat(to_date)
        except ValueError:
            return Response(
                {"error": "to_date must use YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        audit_queryset = audit_queryset.filter(
            changed_at__date__lte=to_date
        )

    if from_date and to_date and from_date > to_date:
        return Response(
            {"error": "from_date cannot be after to_date."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if store_id:
        try:
            store_id_value = int(store_id)
        except ValueError:
            return Response(
                {"error": "store_id must be a valid store ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audit_queryset = audit_queryset.filter(
            item_id__in=Item.objects.filter(
                storeid_id=store_id_value
            ).values("itemid")
        )

    stock_movements = []

    for audit in audit_queryset:
        try:
            old_quantity = int(audit.old_value)
            new_quantity = int(audit.new_value)
        except (TypeError, ValueError):
            continue

        difference = new_quantity - old_quantity

        stock_movements.append({
            "audit_id": audit.audit_id,
            "item_id": audit.item_id,
            "item_name": audit.item_name,
            "action": audit.action,
            "old_quantity": old_quantity,
            "new_quantity": new_quantity,
            "quantity_change": difference,
            "movement_type": (
                "RECEIVED" if audit.action == "RECEIVE"
                else "ISSUED" if audit.action == "ISSUE"
                else "ADJUSTMENT"
            ),
            "changed_at": audit.changed_at.isoformat(),
            "comments": audit.comments,
        })


    request_statuses = list(
        Status.objects.annotate(
            request_count=Count("request")
        ).values("statusname", "request_count")
    )

    request_totals = RequestItem.objects.aggregate(
        total_requested=Sum("qtyrequested"),
    )
    request_totals["total_approved"] = (
        RequestItem.objects.aggregate(total=Sum("quantity_approved"))["total"]
        or 0
    )
    request_totals["total_issued"] = (
        RequestItem.objects.aggregate(total=Sum("qtyissued"))["total"] or 0
    )
    request_totals["legacy_requests_needing_review"] = (
        Request.objects.filter(
            statusid__statusname__in=[
                "Approved", "Partially Issued", "Issued"
            ]
        ).filter(decided_at__isnull=True, legacy_reviewed_at__isnull=True).count()
    )

    monthly_purchases = list(
        Purchase.objects.filter(
            transaction_type=Purchase.TYPE_RECEIPT
        ).annotate(
            month=TruncMonth("purchasedate")
        ).values("month").annotate(
            purchase_count=Count("purchaseid"),
            total_amount=Sum("totalamount"),
        ).order_by("month")
    )

    supplier_totals = list(
        Purchase.objects.filter(
            transaction_type=Purchase.TYPE_RECEIPT
        ).values(
            "supplierid", "supplierid__suppliername"
        ).annotate(
            purchase_count=Count("purchaseid"),
            total_amount=Sum("totalamount"),
        ).order_by("-total_amount")
    )

    grn_count = Grn.objects.count()


    # Staff statistics
    staff_total = Staff.objects.count()

    staff_by_department = list(
        Department.objects.annotate(
            staff_count=Count("staff")
        ).values(
            "departmentid",
            "departmentname",
            "staff_count",
        ).order_by("departmentid")
    )

    staff_by_position = list(
        Position.objects.annotate(
            staff_count=Count("staff")
        ).values(
            "positionid",
            "positionname",
            "staff_count",
        ).order_by("positionid")
    )


    return Response({
        "stores": stores,
        "stock_by_store": stock_by_store,
        "staff_total": staff_total,
        "staff_by_department": staff_by_department,
        "staff_by_position": staff_by_position,
        "request_statuses": request_statuses,
        "request_totals": request_totals,
        "monthly_purchases": [
            {
                "month": row["month"].strftime("%Y-%m")
                if row["month"] else None,
                "purchase_count": row["purchase_count"],
                "total_amount": str(row["total_amount"] or 0),
            }
            for row in monthly_purchases
        ],
        "supplier_totals": [
            {
                "supplier_id": row["supplierid"],
                "supplier_name": row["supplierid__suppliername"],
                "purchase_count": row["purchase_count"],
                "total_amount": str(row["total_amount"] or 0),
            }
            for row in supplier_totals
        ],
        "grn_count": grn_count,

                "stock_movements": stock_movements,
        "movement_filters": {
            "from_date": from_date,
            "to_date": to_date,
            "store_id": store_id,
        },
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
    except (StaffAccount.DoesNotExist, AttributeError):
        return None

    if staff.positionid_id not in MANAGEMENT_POSITIONS:
        return None

    return staff


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def staff_management(request):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage staff."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        staff_members = Staff.objects.select_related(
            "departmentid", "positionid"
        ).order_by("staffid")
        account_by_staff = {
            account.staff_id: account.user.is_active
            and account.user.has_usable_password()
            for account in StaffAccount.objects.select_related("user")
        }
        departments = Department.objects.order_by(
            "departmentid"
        ).values("departmentid", "departmentname")

        positions = Position.objects.order_by(
            "positionid"
        ).values("positionid", "positionname")

        return Response({
            "staff": [
                {
                    "staff_id": person.staffid,
                    "surname": person.surname,
                    "othernames": person.othernames,
                    "department_id": person.departmentid_id,
                    "department": person.departmentid.departmentname,
                    "position_id": person.positionid_id,
                    "position": person.positionid.positionname,
                    "contact": person.contact,
                    "email": person.email or "",
                    "login_ready": account_by_staff.get(person.staffid, False),
                }
                for person in staff_members
            ],
            "departments": list(departments),
            "positions": list(positions),
        })

    data = request.data
    surname = data.get("surname")
    othernames = data.get("othernames")
    contact = data.get("contact")
    email = data.get("email")
    department_id = data.get("department_id")
    position_id = data.get("position_id")

    for field, value in {
        "surname": surname,
        "othernames": othernames,
        "contact": contact,
    }.items():
        if not isinstance(value, str) or not value.strip():
            return Response(
                {"error": f"{field.replace('_', ' ').title()} is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if len(surname.strip()) > 50 or len(othernames.strip()) > 100:
        return Response(
            {"error": "Name is too long."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(contact.strip()) > 20:
        return Response(
            {"error": "Contact cannot exceed 20 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(email, str) or not email.strip():
        return Response(
        {"error": "A staff email address is required to send the account setup link."},
        status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        validate_email(email.strip())
    except ValidationError:
        return Response(
        {"error": "Enter a valid staff email address."},
        status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        department = Department.objects.get(departmentid=department_id)
        position = Position.objects.get(positionid=position_id)
    except (Department.DoesNotExist, Position.DoesNotExist, ValueError, TypeError):
        return Response(
            {"error": "Select a valid department and position."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            person = Staff.objects.create(
                surname=surname.strip(),
                othernames=othernames.strip(),
                contact=contact.strip(),
                departmentid=department,
                positionid=position,
            )
            user = get_user_model().objects.create_user(
                username=str(person.staffid),
                password=None,
                first_name=othernames.strip(),
                last_name=surname.strip(),
            )
            StaffAccount.objects.create(user=user, staff=person)
            person.email = email.strip()
            person.save(update_fields=["email"])
            send_account_setup_email(user, email.strip())
    except (RuntimeError, OSError, smtplib.SMTPException) as error:
        return Response(
            {"error": f"Staff account could not be created because the setup email was not sent: {error}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except IntegrityError:
        return Response(
            {"error": "The staff member or email already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Staff member and login created. A password setup link was emailed.",
            "staff_id": person.staffid,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_staff_setup_email(request, staff_id):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )
    try:
        account = StaffAccount.objects.select_related("user", "staff").get(
            staff_id=staff_id
        )
    except StaffAccount.DoesNotExist:
        return Response(
            {"error": "No invited login account was found for this staff member."},
            status=status.HTTP_404_NOT_FOUND,
        )
    if not account.staff.email:
        return Response(
            {"error": "No email address is recorded for this staff member."},
            status=status.HTTP_409_CONFLICT,
        )
    if account.user.has_usable_password():
        return Response(
            {"error": "This staff member has already set a password."},
            status=status.HTTP_409_CONFLICT,
        )
    try:
        send_account_setup_email(account.user, account.staff.email)
    except (RuntimeError, OSError, smtplib.SMTPException) as error:
        return Response(
            {"error": f"The setup email could not be sent: {error}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({
        "message": f"A new setup link was sent to {account.staff.email}."
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def item_management(request):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage inventory items."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        archived_ids = archived_item_ids()
        items = Item.objects.select_related(
            "storeid", "unitid"
        ).order_by("itemid")

        return Response({
            "items": [
                {
                    "item_id": item.itemid,
                    "item_name": item.itemname,
                    "store_id": item.storeid_id,
                    "store_name": item.storeid.storename,
                    "unit_id": item.unitid_id,
                    "unit_name": item.unitid.unitname,
                    "quantity": item.quantity,
                    "reorder_level": item.reorderlevel,
                    "is_archived": item.itemid in archived_ids,
                }
                for item in items
            ],
            "stores": list(
                Store.objects.order_by("storeid").values(
                    "storeid", "storename"
                )
            ),
            "units": list(
                Unit.objects.order_by("unitid").values(
                    "unitid", "unitname"
                )
            ),
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

    if Item.objects.filter(itemid=item_id).exists():
        return Response(
            {"error": "That item ID already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        store = Store.objects.get(storeid=store_id)
        unit = Unit.objects.get(unitid=unit_id)
    except (Store.DoesNotExist, Unit.DoesNotExist, ValueError, TypeError):
        return Response(
            {"error": "Select a valid store and unit."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        item = Item.objects.create(
            itemid=item_id,
            itemname=item_name.strip(),
            storeid=store,
            unitid=unit,
            quantity=0,
            reorderlevel=reorder_level,
        )
    except IntegrityError:
        return Response(
            {"error": "The item could not be created. Check its ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Item created successfully. Record its opening stock through the approved stock-receiving process.",
            "item_id": item.itemid,
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
        suppliers = Supplier.objects.order_by("supplierid")

        return Response({
            "suppliers": [
                {
                    "supplier_id": supplier.supplierid,
                    "supplier_name": supplier.suppliername,
                    "contact": supplier.contact,
                    "email": supplier.email,
                    "address": supplier.address,
                }
                for supplier in suppliers
            ]
        })

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

    if Supplier.objects.filter(supplierid=supplier_id).exists():
        return Response(
            {"error": "That supplier ID already exists."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        supplier = Supplier.objects.create(
            supplierid=supplier_id,
            suppliername=supplier_name.strip(),
            contact=contact.strip(),
            email=email.strip() or None,
            address=address.strip(),
        )
    except IntegrityError:
        return Response(
            {"error": "The supplier could not be created. Check its ID."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Supplier created successfully.",
            "supplier_id": supplier.supplierid,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_inventory_item(request, item_id):
    staff = get_management_staff(request)

    if staff is None or staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response(
            {"error": "Only the Principal or Store Manager can delete inventory items."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        item = Item.objects.get(itemid=item_id)
    except Item.DoesNotExist:
        return Response(
            {"error": "Inventory item not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Protect historical request records.
    if RequestItem.objects.filter(itemid_id=item_id).exists():
        return Response(
            {"error": "This item cannot be deleted because it has request history."},
            status=status.HTTP_409_CONFLICT,
        )

    # Protect procurement records.
    if PurchaseItem.objects.filter(itemid_id=item_id).exists():
        return Response(
            {"error": "This item cannot be deleted because it has procurement history."},
            status=status.HTTP_409_CONFLICT,
        )

    # Protect inventory audit records.
    if InventoryAudit.objects.filter(item_id=item_id).exists():
        return Response(
            {"error": "This item cannot be deleted because it has audit history."},
            status=status.HTTP_409_CONFLICT,
        )

    if item.quantity != 0:
        return Response(
            {"error": "Only items with zero stock can be deleted."},
            status=status.HTTP_409_CONFLICT,
        )

    item.delete()

    return Response(
        {"message": "Inventory item deleted successfully."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_item_archive_state(request, item_id):
    staff = get_management_staff(request)
    if staff is None or staff.positionid_id not in INVENTORY_MAINTAINER_POSITION_IDS:
        return Response(
            {"error": "Only the Principal or Store Manager can archive items."},
            status=status.HTTP_403_FORBIDDEN,
        )

    action = request.data.get("action")
    reason = request.data.get("reason")
    if action not in {"ARCHIVED", "RESTORED"}:
        return Response(
            {"error": "Choose ARCHIVED or RESTORED."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(reason, str) or not reason.strip():
        return Response(
            {"error": "A reason is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        item = Item.objects.get(itemid=item_id)
    except Item.DoesNotExist:
        return Response(
            {"error": "Inventory item not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    currently_archived = item_id in archived_item_ids()
    if (action == "ARCHIVED" and currently_archived) or (
        action == "RESTORED" and not currently_archived
    ):
        return Response(
            {"error": "The item already has the requested archive state."},
            status=status.HTTP_409_CONFLICT,
        )

    if action == "ARCHIVED":
        request_lines = RequestItem.objects.filter(
            itemid_id=item_id
        ).select_related("requestid", "requestid__statusid")
        for line in request_lines:
            if legacy_approval_requires_review(line.requestid):
                return Response(
                    {"error": "This item has a legacy request awaiting review. Resolve it before archiving."},
                    status=status.HTTP_409_CONFLICT,
                )
            if (
                line.quantity_approved is not None
                and line.qtyissued < line.quantity_approved
            ):
                return Response(
                    {"error": "This item has approved quantities awaiting issue. Complete or resolve them before archiving."},
                    status=status.HTTP_409_CONFLICT,
                )

    old_archived = item.is_archived
    item.is_archived = action == "ARCHIVED"
    item.archived_by_staff_id = staff.staffid if item.is_archived else None
    item.archived_at = timezone.now() if item.is_archived else None
    item.archive_reason = reason.strip() if item.is_archived else None
    with transaction.atomic():
        item.save(update_fields=[
            "is_archived", "archived_by_staff_id", "archived_at",
            "archive_reason",
        ])
        InventoryAudit.objects.create(
            item_id=item.itemid,
            item_name=item.itemname,
            action=action,
            field_changed="is_archived",
            old_value=str(old_archived),
            new_value=str(item.is_archived),
            comments=reason.strip(),
            changed_by=request.user,
            changed_by_staff_id=staff.staffid,
        )
    return Response({
        "message": (
            "Item archived. It is hidden from new requests and receiving."
            if action == "ARCHIVED"
            else "Item restored and available for requests and receiving."
        ),
        "item_id": item.itemid,
        "is_archived": action == "ARCHIVED",
    })
