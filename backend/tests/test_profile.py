"""Profile endpoint tests for Hamburg Apartment Scanner.
Covers: GET /api/profile, PUT /api/profile, and /api/auth/me notification fields.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hamburg-listings.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@hamburg-scanner.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def user_session(admin_session):
    email = f"test_profile_{uuid.uuid4().hex[:8]}@example.com"
    password = "user12345"
    r = admin_session.post(
        f"{BASE_URL}/api/admin/users",
        json={"email": email, "password": password, "name": "TEST Profile", "role": "user"},
        timeout=15,
    )
    assert r.status_code == 200, f"create user failed: {r.text}"
    uid = r.json()["id"]

    us = requests.Session()
    r = us.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200
    us._email = email
    yield us
    try:
        admin_session.delete(f"{BASE_URL}/api/admin/users/{uid}", timeout=15)
    except Exception:
        pass


class TestProfile:
    def test_profile_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/profile", timeout=15)
        assert r.status_code == 401

    def test_get_profile_default(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/profile", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email"] == user_session._email
        # default notification_email falls back to login email
        assert d["notification_email"] == user_session._email
        assert d["notifications_enabled"] is False
        assert "id" in d

    def test_put_profile_update_and_persistence(self, user_session):
        new_email = f"notify_{uuid.uuid4().hex[:6]}@example.com"
        payload = {"notification_email": new_email, "notifications_enabled": True}
        r = user_session.put(f"{BASE_URL}/api/profile", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["notifications_enabled"] is True
        assert d["notification_email"] == new_email

        # GET verifies persistence
        r2 = user_session.get(f"{BASE_URL}/api/profile", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["notification_email"] == new_email
        assert d2["notifications_enabled"] is True

    def test_put_profile_disable(self, user_session):
        # Keep notification_email but disable notifications
        r = user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notification_email": user_session._email, "notifications_enabled": False},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json()["notifications_enabled"] is False

        r2 = user_session.get(f"{BASE_URL}/api/profile", timeout=15)
        assert r2.json()["notifications_enabled"] is False

    def test_put_profile_invalid_email(self, user_session):
        r = user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notification_email": "not-an-email", "notifications_enabled": True},
            timeout=15,
        )
        assert r.status_code == 422

    def test_auth_me_includes_notification_fields(self, user_session):
        # First enable
        user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notification_email": user_session._email, "notifications_enabled": True},
            timeout=15,
        )
        r = user_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "notification_email" in d
        assert "notifications_enabled" in d
        assert d["notifications_enabled"] is True


class TestRegression:
    """Spot-check that previous functionality still works after profile changes."""

    def test_admin_login_still_works(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_apartments_endpoint(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_manual_urls_endpoint(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/manual-urls", timeout=15)
        assert r.status_code == 200

    def test_scan_status_endpoint(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/scan-status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("is_scanning", "total_apartments", "new_apartments"):
            assert k in d
