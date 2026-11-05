
from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.staff_login, name="staff_login"),
    path("requests/", views.create_request, name="create_request"),
    path("session/", views.check_session, name="check_session"),
    path("csrf/", views.csrf_token, name="csrf_token"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("inventory/", views.inventory_list, name="inventory_list"),
    path(
    "inventory/<int:item_id>/edit/",
    views.edit_inventory_item,
    name="edit_inventory_item"),
    path("my-requests/", views.my_requests, name="my_requests"),
    path(
    "requests/drafts/",
    views.save_request_draft,
    name="save_request_draft",),
    path(
    "requests/<int:request_id>/draft/",
    views.edit_request_draft,
    name="edit_request_draft",),
    path(
    "requests/<int:request_id>/delete-draft/",
    views.delete_request_draft,
    name="delete_request_draft",),
    path(
    "requests/<int:request_id>/submit/",
    views.submit_request_draft,
    name="submit_request_draft",),
    path(
    "requestable-items/",
    views.requestable_items,
    name="requestable_items",),
    path("pending-requests/", views.pending_requests, name="pending_requests"),
    path(
        "requests/<int:request_id>/approve/",
        views.approve_request,
        name="approve_request",
    ),
    path(
        "requests/<int:request_id>/reject/",
        views.reject_request,
        name="reject_request",
    ),
    path(
    "reports/",
    views.reports_dashboard,
    name="reports_dashboard",
    ),
    path(
    "receiving/options/",
    views.receiving_options,
    name="receiving_options",
    ),
    path(
        "receiving/receive/",
        views.receive_goods,
        name="receive_goods",
    ),
    path(
    "reports/",
    views.reports_dashboard,
    name="reports_dashboard",
    ),
    path("management/staff/", views.staff_management, name="staff_management"),
    path("management/items/", views.item_management, name="item_management"),
    path("management/suppliers/", views.supplier_management, name="supplier_management"),
    path(
    "inventory/<int:item_id>/delete/",
    views.delete_inventory_item,
    name="delete_inventory_item",),
]
