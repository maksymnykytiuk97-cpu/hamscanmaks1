"""Backend tests for Hamburg Apartment Scanner.
Covers: auth (login/me/logout), apartments (filters), scan endpoints,
admin endpoints (users CRUD, manual URLs CRUD), and admin-only RBAC.
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hamburg-listings.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@hamburg-scanner.com"
ADMIN_PASSWORD = "admin123"

TEST_URL_1 = "https://tenant.immomio.com/apply/5650db80-3372-44de-b759-4b0b9dd1a4bb"
TEST_URL_2 = "https://tenant.immomio.com/apply/2788b147-3f34-4a25-9a21-5e4031134331"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    assert "access_token" in s.cookies, f"No access_token cookie set: {dict(s.cookies)}"
    return s


@pytest.fixture(scope="session")
def user_session(admin_session):
    """Create a non-admin user then log in as them."""
    email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "user12345"
    r = admin_session.post(
        f"{BASE_URL}/api/admin/users",
        json={"email": email, "password": password, "name": "TEST User", "role": "user"},
        timeout=15,
    )
    assert r.status_code == 200, f"create user failed: {r.text}"
    user_id = r.json()["id"]

    us = requests.Session()
    r = us.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    us._created_id = user_id
    us._created_email = email
    yield us
    # cleanup
    try:
        admin_session.delete(f"{BASE_URL}/api/admin/users/{user_id}", timeout=15)
    except Exception:
        pass


# ---------- Auth ----------
class TestAuth:
    def test_login_success_sets_cookies(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "id" in data
        assert "access_token" in s.cookies
        assert "refresh_token" in s.cookies

    def test_login_invalid_credentials(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me_returns_admin(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == ADMIN_EMAIL
        assert d["role"] == "admin"

    def test_me_unauthenticated(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 401


# ---------- Apartments ----------
class TestApartments:
    def test_apartments_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/apartments", timeout=15)
        assert r.status_code == 401

    def test_apartments_list_authenticated(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_apartments_filters(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/apartments",
            params={"min_price": 100, "max_price": 5000, "min_rooms": 1, "max_rooms": 10, "status": "new"},
            timeout=15,
        )
        assert r.status_code == 200
        for apt in r.json():
            if apt.get("price") is not None:
                assert 100 <= apt["price"] <= 5000
            if apt.get("rooms") is not None:
                assert 1 <= apt["rooms"] <= 10
            assert apt.get("status") == "new"

    def test_apartments_history(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments/history", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    # --- New: multi-landlord (GraphQL) real-data assertions ---
    def test_apartments_count_at_least_12(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20)
        assert r.status_code == 200
        apts = r.json()
        assert len(apts) >= 12, f"Expected >=12 apartments, got {len(apts)}"

    def test_apartments_have_required_fields(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20)
        assert r.status_code == 200
        apts = r.json()
        assert apts, "no apartments returned"
        required_present = ["title", "url"]
        for apt in apts:
            for f in required_present:
                assert apt.get(f), f"Missing field {f} in apt {apt.get('id')}"
            assert isinstance(apt.get("url"), str)
            # immomio apply URL pattern
            assert "tenant.immomio.com/apply/" in apt["url"], f"Unexpected URL: {apt['url']}"

    def test_apartments_multiple_landlords(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20)
        assert r.status_code == 200
        apts = r.json()
        landlords = {a.get("landlord") for a in apts if a.get("landlord")}
        # expect at least 3 of the 4 known GraphQL landlords
        expected = {"BGFG", "Hamburger Wohnen", "BDS Hamburg", "VHW Hamburg"}
        overlap = landlords & expected
        assert len(overlap) >= 3, f"Expected >=3 known landlords, got {landlords}"

    def test_apartments_rooms_can_be_float(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20)
        assert r.status_code == 200
        apts = r.json()
        # rooms should be numeric (float allowed). Verify no parking (rooms==0) leaks through.
        for a in apts:
            if a.get("rooms") is not None:
                assert isinstance(a["rooms"], (int, float))
                assert a["rooms"] > 0, f"rooms==0 leaked (parking?) for {a.get('id')}"

    def test_filter_min_price(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", params={"min_price": 500}, timeout=20)
        assert r.status_code == 200
        for a in r.json():
            if a.get("price") is not None:
                assert a["price"] >= 500

    def test_filter_max_price(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", params={"max_price": 1500}, timeout=20)
        assert r.status_code == 200
        for a in r.json():
            if a.get("price") is not None:
                assert a["price"] <= 1500

    def test_filter_rooms_float_range(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/apartments",
            params={"min_rooms": 1, "max_rooms": 2.5},
            timeout=20,
        )
        assert r.status_code == 200
        for a in r.json():
            if a.get("rooms") is not None:
                assert 1 <= a["rooms"] <= 2.5


# ---------- Scan status reflects multi-landlord data ----------
class TestScanStatusCount:
    def test_total_apartments_at_least_12(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/scan-status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total_apartments"] >= 12, f"total_apartments={d['total_apartments']}"


# ---------- Scan endpoints ----------
class TestScan:
    def test_scan_status(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/scan-status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("is_scanning", "total_apartments", "new_apartments"):
            assert k in d
        assert isinstance(d["total_apartments"], int)
        assert isinstance(d["new_apartments"], int)

    def test_scan_now_triggers(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/scan-now", timeout=15)
        # 200 if started, 400 if already running
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert "message" in r.json()


# ---------- Admin: Users ----------
class TestAdminUsers:
    def test_list_users_admin_only(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert any(u["email"] == ADMIN_EMAIL for u in users)

    def test_list_users_unauthenticated_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 401

    def test_list_users_non_admin_403(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 403

    def test_create_and_delete_user(self, admin_session):
        email = f"test_crud_{uuid.uuid4().hex[:8]}@example.com"
        r = admin_session.post(
            f"{BASE_URL}/api/admin/users",
            json={"email": email, "password": "abc12345", "name": "TEST CRUD", "role": "user"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        uid = r.json()["id"]
        assert r.json()["email"] == email

        # duplicate -> 400
        r2 = admin_session.post(
            f"{BASE_URL}/api/admin/users",
            json={"email": email, "password": "abc12345", "name": "dup", "role": "user"},
            timeout=15,
        )
        assert r2.status_code == 400

        # verify in list
        lst = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15).json()
        assert any(u["id"] == uid for u in lst)

        # delete
        rd = admin_session.delete(f"{BASE_URL}/api/admin/users/{uid}", timeout=15)
        assert rd.status_code == 200

        lst2 = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15).json()
        assert not any(u["id"] == uid for u in lst2)


# ---------- Admin: Manual URLs ----------
class TestManualUrls:
    def test_list_urls_non_admin_403(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/admin/manual-urls", timeout=15)
        assert r.status_code == 403

    def test_add_invalid_url_rejected(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/manual-urls",
            json={"url": "https://example.com/some/path"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_add_list_and_remove_url(self, admin_session):
        unique_url = f"https://tenant.immomio.com/apply/{uuid.uuid4()}"
        # add
        r = admin_session.post(f"{BASE_URL}/api/admin/manual-urls", json={"url": unique_url}, timeout=15)
        assert r.status_code == 200, r.text

        # duplicate
        rd = admin_session.post(f"{BASE_URL}/api/admin/manual-urls", json={"url": unique_url}, timeout=15)
        assert rd.status_code == 400

        # list
        urls = admin_session.get(f"{BASE_URL}/api/admin/manual-urls", timeout=15).json()
        assert any(item["url"] == unique_url for item in urls)

        # remove (DELETE with body)
        rr = admin_session.delete(f"{BASE_URL}/api/admin/manual-urls", json={"url": unique_url}, timeout=15)
        assert rr.status_code == 200

        # remove again -> 404
        rr2 = admin_session.delete(f"{BASE_URL}/api/admin/manual-urls", json={"url": unique_url}, timeout=15)
        assert rr2.status_code == 404


# ---------- Logout ----------
class TestLogout:
    def test_logout_clears_session(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert r.status_code == 200
