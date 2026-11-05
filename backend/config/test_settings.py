from .settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "school-store@example.test"
EMAIL_HOST = "smtp.example.test"
FRONTEND_URL = "http://localhost:5173"
SECRET_KEY = "test-only-secret-key"
