
from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.staff_login, name="staff_login"),
    path("requests/", views.create_request, name="create_request"),
    path("session/", views.check_session, name="check_session"),
    path("logout/", views.staff_logout, name="staff_logout"),
    path(
        "management/staff/<int:staff_id>/invite/",
        views.resend_staff_setup_email,
        name="resend_staff_setup_email",
    ),
    path(
        "account/setup/",
        views.complete_staff_account_setup,
        name="complete_staff_account_setup",
    ),
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
        "request-issue-history/",
        views.request_issue_history,
        name="request_issue_history",
    ),
    path("pending-issues/", views.pending_issues, name="pending_issues"),
    path(
        "requests/<int:request_id>/legacy-review/",
        views.reconcile_legacy_request,
        name="reconcile_legacy_request",
    ),
    path(
        "requests/<int:request_id>/issue/",
        views.issue_request,
        name="issue_request",
    ),
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
    path("purchase-orders/", views.purchase_orders, name="purchase_orders"),
    path(
        "pending-purchase-orders/",
        views.pending_purchase_orders,
        name="pending_purchase_orders",
    ),
    path(
        "purchase-orders/<int:order_id>/decision/",
        views.decide_purchase_order,
        name="decide_purchase_order",
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
    path(
        "management/items/<int:item_id>/archive/",
        views.set_item_archive_state,
        name="set_item_archive_state",
    ),
    path("management/suppliers/", views.supplier_management, name="supplier_management"),
    path(
    "inventory/<int:item_id>/delete/",
    views.delete_inventory_item,
    name="delete_inventory_item",),
]
