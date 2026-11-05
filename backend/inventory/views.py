
from datetime import date

from django.contrib.auth import authenticate, login
from django.db import transaction

from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Request, RequestItem, Status, StaffAccount, Staff, Department, Position, Store, Item, Unit, InventoryAudit
from .serializers import RequestSerializer

from decimal import Decimal, InvalidOperation
from django.db import IntegrityError
from django.db.models import Max

from django.db.models import Count, Sum
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

    allowed_stores = {
        1: [3],        # Teacher
        2: [1],        # Cleaner
        4: [1],        # Support Staff
        8: [1, 2, 3],  # Procurement Officer
        9: [1, 2],     # Chef
    }

    store_ids = allowed_stores.get(position_id, [])

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
        "can_approve": position_id in [5, 6, 7],
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
    allowed_positions = [5, 6, 7, 8]

    if staff.positionid_id not in allowed_positions:
        return Response(
            {"error": "You are not authorized to view inventory."},
            status=status.HTTP_403_FORBIDDEN,
        )

    items = Item.objects.select_related(
        "storeid", "unitid"
    ).order_by("itemid")

    results = []
    for item in items:
        results.append({
            "item_id": item.itemid,
            "item_name": item.itemname,
            "store_id": item.storeid_id,
            "store_name": item.storeid.storename,
            "unit_id": item.unitid_id,
            "quantity": item.quantity,
            "reorder_level": item.reorderlevel,
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

    # Only the Principal (5) and Store Manager (7) may edit inventory.
    if staff.positionid_id not in [5, 7]:
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
                action="EDIT",
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

        results.append({
            "request_id": req.requestid,
            "store_id": req.storeid_id,
            "store_name": req.storeid.storename,
            "request_date": req.requestdate,
            "status_id": req.statusid_id,
            "status": req.statusid.statusname,
            "items": [
                {
                    "item_id": line.itemid_id,
                    "item_name": line.itemid.itemname,
                    "quantity_requested": line.qtyrequested,
                    "quantity_issued": line.qtyissued,
                }
                for line in request_items
            ],
        })

    return Response({"requests": results})


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

    allowed_stores = {
        1: [3],       # Teacher → Scholastics
        2: [1],       # Cleaner → Cleaning
        4: [1],       # Support Staff → Cleaning
        5: [1, 2, 3], # Principal → all stores
        8: [1, 2, 3], # Procurement Officer → all stores
        9: [1, 2],    # Chef → Cleaning and Food
    }

    store_ids = allowed_stores.get(staff.positionid_id, [])

    items = (
        Item.objects
        .filter(storeid_id__in=store_ids)
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
    if staff.positionid_id not in [5, 6, 7]:
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
                    "quantity_issued": line.qtyissued,
                }
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

    if staff.positionid_id not in [5, 6, 7]:
        return Response(
            {"error": "You are not authorized to approve requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    approved_items = request.data.get("items")

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

        partially_approved = False

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

            if quantity < line.qtyrequested:
                partially_approved = True

            # Project convention: qtyissued stores the approved quantity.
            line.qtyissued = quantity

        approved_status_name = (
            "Partially Issued" if partially_approved else "Approved"
        )

        new_status = Status.objects.filter(
            statusname__iexact=approved_status_name
        ).first()

        if new_status is None:
            return Response(
                {"error": f"{approved_status_name} status is not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        RequestItem.objects.bulk_update(lines, ["qtyissued"])

        req.statusid = new_status
        req.approvedby = staff
        req.save(update_fields=["statusid", "approvedby"])

    return Response({
        "message": "Request quantities approved successfully.",
        "request_id": req.requestid,
        "status": approved_status_name,
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

    if staff.positionid_id not in [5, 6, 7]:
        return Response(
            {"error": "You are not authorized to reject requests."},
            status=status.HTTP_403_FORBIDDEN,
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
        req.save(update_fields=["statusid", "approvedby"])

    return Response({
        "message": "Request rejected successfully.",
        "request_id": req.requestid,
        "status": "Rejected",
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

    if staff.positionid_id != 7:
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

    items = [
        {
            "item_id": item.itemid,
            "item_name": item.itemname,
            "store_id": item.storeid_id,
            "store_name": item.storeid.storename,
            "quantity_in_stock": item.quantity,
            "unit_id": item.unitid_id,
        }
        for item in Item.objects.select_related(
            "storeid", "unitid"
        ).order_by("itemname")
    ]

    return Response({
        "stores": stores,
        "suppliers": suppliers,
        "items": items,
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

    if staff.positionid_id != 7:
        return Response(
            {"error": "Only the Store Manager can receive goods."},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = request.data

    store_id = data.get("store_id")
    supplier_id = data.get("supplier_id")
    invoice_number = data.get("invoice_number")
    grn_number = data.get("grn_number")
    remarks = data.get("remarks", "")
    raw_items = data.get("items")

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
    except (Store.DoesNotExist, Supplier.DoesNotExist):
        return Response(
            {"error": "The selected store or supplier does not exist."},
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

            purchase = Purchase.objects.create(
                storeid=store,
                supplierid=supplier,
                staffid=staff,
                invoicenumber=invoice_number,
                invoicedate=parsed_dates["invoice_date"],
                purchasedate=parsed_dates["purchase_date"],
                totalamount=total_amount,
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
                    unitcost=entry["unit_cost"],
                    quantity=entry["quantity"],
                )

            grn = Grn.objects.create(
                purchaseid=purchase,
                grnnumber=grn_number,
                grndate=parsed_dates["grn_date"],
                staffid=staff,
                remarks=remarks.strip(),
            )

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
    if position_id not in [5, 6, 7, 8]:
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
                "IN" if difference > 0
                else "OUT" if difference < 0
                else "NO CHANGE"
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
        total_issued=Sum("qtyissued"),
    )

    monthly_purchases = list(
        Purchase.objects.annotate(
            month=TruncMonth("purchasedate")
        ).values("month").annotate(
            purchase_count=Count("purchaseid"),
            total_amount=Sum("totalamount"),
        ).order_by("month")
    )

    supplier_totals = list(
        Purchase.objects.values(
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


MANAGEMENT_POSITIONS = [5, 7, 8]
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

    try:
        department = Department.objects.get(departmentid=department_id)
        position = Position.objects.get(positionid=position_id)
    except (Department.DoesNotExist, Position.DoesNotExist, ValueError, TypeError):
        return Response(
            {"error": "Select a valid department and position."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        person = Staff.objects.create(
            surname=surname.strip(),
            othernames=othernames.strip(),
            contact=contact.strip(),
            departmentid=department,
            positionid=position,
        )
    except IntegrityError:
        return Response(
            {"error": "The staff member could not be created."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "message": "Staff member created successfully.",
            "staff_id": person.staffid,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def item_management(request):
    if get_management_staff(request) is None:
        return Response(
            {"error": "You are not authorized to manage inventory items."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
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

    if staff is None or staff.positionid_id not in [5, 7]:
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
