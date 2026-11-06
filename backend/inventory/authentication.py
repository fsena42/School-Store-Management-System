import hashlib
import secrets
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication

from .models import Staff
from .sql import fetch_one


SESSION_COOKIE = "school_store_session"
SESSION_MAX_AGE = 8 * 60 * 60


def staff_principal(row):
    staff = Staff(
        staffid=row["StaffID"],
        surname=row["SurName"],
        othernames=row["OtherNames"],
        positionid_id=row["PositionID"],
        is_active=bool(row["IsActive"]),
    )
    staff.id = staff.staffid
    staff.is_authenticated = True
    staff.is_anonymous = False
    staff.position = row["PositionName"]
    staff.staff_account = SimpleNamespace(staff=staff)
    return staff


class StaffCookieAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw_token = request.COOKIES.get(SESSION_COOKIE)
        if not raw_token:
            return None

        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        row = fetch_one(
            """
            SELECT s.StaffID, s.SurName, s.OtherNames, s.PositionID,
                   p.PositionName, s.IsActive
            FROM staff AS s
            JOIN position AS p ON p.PositionID = s.PositionID
            WHERE s.SessionTokenHash = %s
              AND s.SessionExpiresAt > %s
              AND s.IsActive = 1
            """,
            [token_hash, timezone.now()],
        )
        if row is None:
            return None
        return staff_principal(row), raw_token

    def authenticate_header(self, request):
        return "Session"


def new_session_token():
    return secrets.token_urlsafe(32)


def session_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry():
    return timezone.now() + timedelta(seconds=SESSION_MAX_AGE)
