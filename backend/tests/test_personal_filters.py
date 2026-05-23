"""Tests for personal filters (per-user) and direct landlord scrapers (Vonovia, Walddörfer).

Covers iteration 5 changes:
- GET /api/profile returns min_price, max_price, min_rooms, max_rooms
- PUT /api/profile saves & persists the 4 filter fields
- Vonovia/Walddörfer apartments are stored with correct landlord & URL pointing
  to their own site (NOT immomio).
- /api/apartments still aggregates all landlords.
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hamburg-listings.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@hamburg-scanner.com"
ADMIN_PASSWORD = "admin123"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def user_session(admin_session):
    email = f"test_pf_{uuid.uuid4().hex[:8]}@example.com"
    password = "user12345"
    r = admin_session.post(
        f"{BASE_URL}/api/admin/users",
        json={"email": email, "password": password, "name": "TEST PF", "role": "user"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
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


# ---------- profile personal filter fields ----------
class TestProfilePersonalFilters:
    def test_profile_includes_filter_fields_default_null(self, user_session):
        r = user_session.get(f"{BASE_URL}/api/profile", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("min_price", "max_price", "min_rooms", "max_rooms"):
            assert k in d, f"missing key {k} in /api/profile"
            assert d[k] is None, f"{k} expected None for new user, got {d[k]}"

    def test_put_profile_saves_filters_and_persists(self, user_session):
        payload = {
            "notification_email": user_session._email,
            "notifications_enabled": False,
            "min_price": 500,
            "max_price": 1500,
            "min_rooms": 1.5,
            "max_rooms": 3.5,
        }
        r = user_session.put(f"{BASE_URL}/api/profile", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["min_price"] == 500
        assert d["max_price"] == 1500
        assert d["min_rooms"] == 1.5
        assert d["max_rooms"] == 3.5

        # GET verifies persistence
        r2 = user_session.get(f"{BASE_URL}/api/profile", timeout=15)
        d2 = r2.json()
        assert d2["min_price"] == 500
        assert d2["max_price"] == 1500
        assert d2["min_rooms"] == 1.5
        assert d2["max_rooms"] == 3.5

    def test_put_profile_clears_filters_with_null(self, user_session):
        # Save then clear
        user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notifications_enabled": False, "min_price": 800, "max_price": 2000,
                  "min_rooms": 2, "max_rooms": 4},
            timeout=15,
        )
        r = user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notifications_enabled": False, "min_price": None, "max_price": None,
                  "min_rooms": None, "max_rooms": None},
            timeout=15,
        )
        assert r.status_code == 200
        d = user_session.get(f"{BASE_URL}/api/profile", timeout=15).json()
        for k in ("min_price", "max_price", "min_rooms", "max_rooms"):
            assert d[k] is None

    def test_filters_are_per_user(self, admin_session, user_session):
        # user sets filters
        user_session.put(
            f"{BASE_URL}/api/profile",
            json={"notifications_enabled": False, "min_price": 700, "max_price": 1800,
                  "min_rooms": 2, "max_rooms": 3},
            timeout=15,
        )
        # admin's profile should NOT have those values
        ar = admin_session.get(f"{BASE_URL}/api/profile", timeout=15).json()
        # admin may have its own values but should not equal the user's combo as a side-effect
        not_equal = not (
            ar.get("min_price") == 700 and ar.get("max_price") == 1800
            and ar.get("min_rooms") == 2 and ar.get("max_rooms") == 3
        )
        assert not_equal, f"Admin profile leaked user filters: {ar}"


# ---------- direct landlord scrapers (Vonovia, Walddörfer) ----------
class TestDirectLandlords:
    def test_apartments_endpoint_returns_data(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20)
        assert r.status_code == 200
        apts = r.json()
        assert isinstance(apts, list)
        assert len(apts) > 0, "no apartments in DB"

    def test_vonovia_apartments_have_correct_landlord_and_url(self, admin_session):
        apts = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20).json()
        vonovia = [a for a in apts if (a.get("landlord") or "").lower() == "vonovia"]
        if not vonovia:
            pytest.skip("No Vonovia apartments in DB at the moment")
        for a in vonovia[:5]:
            url = a.get("url", "")
            assert "vonovia.de" in url, f"Vonovia apt URL must point to vonovia.de, got {url}"
            assert "tenant.immomio.com" not in url, "Vonovia apt should NOT point to immomio"

    def test_walddoerfer_apartments_have_correct_landlord_and_url(self, admin_session):
        apts = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20).json()
        wald = [a for a in apts if (a.get("landlord") or "").lower().startswith("walddörfer")
                or (a.get("landlord") or "").lower().startswith("walddoerfer")]
        if not wald:
            pytest.skip("No Walddörfer apartments in DB at the moment")
        for a in wald[:5]:
            url = a.get("url", "")
            assert "walddoerfer.de" in url, f"Walddörfer URL must point to walddoerfer.de, got {url}"
            assert "tenant.immomio.com" not in url

    def test_apartments_contain_multiple_landlord_sources(self, admin_session):
        """Aggregation: list must include landlords beyond immomio-only ones."""
        apts = admin_session.get(f"{BASE_URL}/api/apartments", timeout=20).json()
        landlords = {(a.get("landlord") or "").strip() for a in apts if a.get("landlord")}
        # At least 2 distinct landlord sources expected (e.g. Vonovia + an immomio one)
        assert len(landlords) >= 2, f"Expected multi-landlord aggregation, got: {landlords}"


# ---------- regression: NEU badge cutoff (status=new) ----------
class TestRegression:
    def test_status_new_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", params={"status": "new"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_status_history_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/apartments", params={"status": "history"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_endpoints_still_work(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
