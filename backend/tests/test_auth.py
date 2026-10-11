"""Sign-up, login, logout, sessions, permissions and per-user isolation."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute

from app.core.security import hash_password, verify_password
from app.main import app
from app.models.user import AuthSession, User
from tests.conftest import DEFAULT_EMAIL, TEST_PASSWORD

# Routes reachable without a session. Everything else must return 401.
PUBLIC_ROUTES = {"/health", "/api/auth/signup", "/api/auth/login", "/api/auth/logout"}


def _upload_csv(client, simple_csv):
    with open(simple_csv, "rb") as f:
        response = client.post("/api/workbooks", files={"file": ("data.csv", f, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- passwords -------------------------------------------------------------


def test_password_hash_round_trip_and_salting():
    first, second = hash_password("s3cret-pass"), hash_password("s3cret-pass")
    assert first != second  # random salt
    assert "s3cret-pass" not in first
    assert verify_password("s3cret-pass", first)
    assert not verify_password("wrong-pass1", first)
    assert not verify_password("s3cret-pass", "garbage")


def test_password_is_stored_hashed(client):
    with client.test_sessionmaker() as db:
        user = db.query(User).filter(User.email == DEFAULT_EMAIL).one()
        assert user.password_hash.startswith("scrypt$")
        assert TEST_PASSWORD not in user.password_hash


# --- sign up -----------------------------------------------------------------


def test_signup_sets_httponly_session_cookie(anon_client):
    response = anon_client.post("/api/auth/signup", json={"email": "New@Example.com", "password": "abcdefg1"})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"  # normalised
    assert body["role"] == "owner"
    assert "records:approve" in body["permissions"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert anon_client.get("/api/auth/me").status_code == 200


def test_signup_duplicate_email_is_409(client, anon_client):
    response = anon_client.post("/api/auth/signup", json={"email": DEFAULT_EMAIL.upper(), "password": "abcdefg1"})
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "abcdefg1"},
        {"email": "a@b.co", "password": "short1"},
        {"email": "a@b.co", "password": "lettersonly"},
        {"email": "a@b.co", "password": "12345678"},
        {"email": "a@b.co"},
    ],
)
def test_signup_validation(anon_client, payload):
    assert anon_client.post("/api/auth/signup", json=payload).status_code == 422


def test_each_signup_gets_its_own_tenant(client, make_client):
    make_client("second@example.com")
    with client.test_sessionmaker() as db:
        tenants = {u.tenant_id for u in db.query(User).all()}
    assert len(tenants) == 2


# --- login / logout ----------------------------------------------------------


def test_login_success(client, anon_client):
    response = anon_client.post("/api/auth/login", json={"email": DEFAULT_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 200
    assert anon_client.get("/api/auth/me").json()["email"] == DEFAULT_EMAIL


def test_login_wrong_password_and_unknown_email_look_identical(client, anon_client):
    wrong = anon_client.post("/api/auth/login", json={"email": DEFAULT_EMAIL, "password": "nope-nope-1"})
    unknown = anon_client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-1"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"


def test_login_is_throttled_after_repeated_failures(client, anon_client):
    for _ in range(10):
        anon_client.post("/api/auth/login", json={"email": DEFAULT_EMAIL, "password": "nope-nope-1"})
    blocked = anon_client.post("/api/auth/login", json={"email": DEFAULT_EMAIL, "password": TEST_PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["error_code"] == "TOO_MANY_ATTEMPTS"


def test_logout_invalidates_the_session_server_side(client):
    cookie = client.cookies.get("s2p_session")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    # Replaying the old cookie no longer works either.
    client.cookies.set("s2p_session", cookie)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "SESSION_EXPIRED"


def test_expired_session_is_rejected(client):
    with client.test_sessionmaker() as db:
        db.query(AuthSession).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
        db.commit()
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "SESSION_EXPIRED"


def test_forged_cookie_is_rejected(anon_client):
    anon_client.cookies.set("s2p_session", "made-up-token")
    assert anon_client.get("/api/auth/me").json()["detail"]["error_code"] == "SESSION_EXPIRED"


def test_session_tokens_are_stored_hashed(client):
    cookie = client.cookies.get("s2p_session")
    with client.test_sessionmaker() as db:
        stored = [s.token_hash for s in db.query(AuthSession).all()]
    assert cookie not in stored


# --- every route is protected -----------------------------------------------


def _protected_routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path not in PUBLIC_ROUTES:
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def test_every_api_route_requires_a_session(anon_client):
    checked = 0
    for method, path in _protected_routes():
        url = path.replace("{workbook_id}", str(uuid.uuid4())).replace("{record_id}", str(uuid.uuid4()))
        url = url.replace("{worksheet_name}", "Sheet1")
        response = anon_client.request(method, url)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
        checked += 1
    assert checked >= 10


# --- isolation ---------------------------------------------------------------


def test_users_only_list_their_own_workbooks(client, make_client, simple_csv):
    mine = _upload_csv(client, simple_csv)
    other = make_client("other@example.com")
    theirs = _upload_csv(other, simple_csv)
    assert [w["id"] for w in client.get("/api/workbooks").json()] == [mine]
    assert [w["id"] for w in other.get("/api/workbooks").json()] == [theirs]


def test_other_user_cannot_read_or_change_my_workbook(client, make_client, simple_csv):
    workbook_id = _upload_csv(client, simple_csv)
    other = make_client("other@example.com")
    base = f"/api/workbooks/{workbook_id}"
    assert other.get(base).status_code == 404
    assert other.get(f"{base}/portal").status_code == 404
    assert other.get(f"{base}/worksheets/data/records").status_code == 404
    assert other.patch(base, json={"title": "pwned"}).status_code == 404
    assert client.get(base).json()["display_title"] is None


# --- permissions -------------------------------------------------------------


def test_viewer_can_read_but_not_upload(client, make_client, simple_csv):
    viewer = make_client("viewer@example.com", role="viewer")
    with open(simple_csv, "rb") as f:
        response = viewer.post("/api/workbooks", files={"file": ("data.csv", f, "text/csv")})
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "FORBIDDEN"
    assert viewer.get("/api/workbooks").status_code == 200
    me = viewer.get("/api/auth/me").json()
    assert me["permissions"] == ["view"]
