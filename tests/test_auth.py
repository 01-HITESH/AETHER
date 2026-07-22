from __future__ import annotations

from fastapi.testclient import TestClient

from BACKEND.services.security import token_hash, totp_code
from tests.conftest import DEFAULT_PASSWORD


def test_register_login_logout_and_session_expiry(app, client, register_user):
    response = register_user(client)
    user = response.json()["user"]
    assert user["email"] == "designer@example.com"
    assert user["name"] == "Test Designer"

    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=strict" in cookie_header
    assert client.get("/api/me").status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/me").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": DEFAULT_PASSWORD},
    )
    assert login.status_code == 200
    raw_token = client.cookies.get(app.state.settings.cookie_name)
    assert raw_token

    with app.state.database.connect() as connection:
        connection.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            ("2000-01-01T00:00:00+00:00", token_hash(raw_token)),
        )

    assert client.get("/api/me").status_code == 401
    with app.state.database.connect() as connection:
        expired = connection.execute(
            "SELECT token_hash FROM sessions WHERE token_hash = ?",
            (token_hash(raw_token),),
        ).fetchone()
    assert expired is None


def test_password_change_revokes_every_active_session(app, client, register_user):
    register_user(client)
    secondary = TestClient(app)
    try:
        login = secondary.post(
            "/api/auth/login",
            json={"email": "designer@example.com", "password": DEFAULT_PASSWORD},
        )
        assert login.status_code == 200
        assert secondary.get("/api/me").status_code == 200

        changed = client.patch(
            "/api/me/password",
            json={
                "currentPassword": DEFAULT_PASSWORD,
                "newPassword": "updated-correct-horse-456",
            },
        )
        assert changed.status_code == 200
        assert changed.json() == {"ok": True, "reauthenticate": True}

        assert client.get("/api/me").status_code == 401
        assert secondary.get("/api/me").status_code == 401
        assert secondary.post(
            "/api/auth/login",
            json={"email": "designer@example.com", "password": DEFAULT_PASSWORD},
        ).status_code == 401
        assert secondary.post(
            "/api/auth/login",
            json={
                "email": "designer@example.com",
                "password": "updated-correct-horse-456",
            },
        ).status_code == 200
    finally:
        secondary.close()


def test_two_factor_setup_enforces_login_challenge(client, register_user):
    register_user(client)
    setup = client.post("/api/me/two-factor/setup")
    assert setup.status_code == 200
    secret = setup.json()["secret"]

    enabled = client.post(
        "/api/me/two-factor/enable",
        json={"code": totp_code(secret)},
    )
    assert enabled.status_code == 200
    assert enabled.json()["user"]["two_factor_enabled"] is True

    assert client.post("/api/auth/logout").status_code == 200
    required = client.post(
        "/api/auth/login",
        json={"email": "designer@example.com", "password": DEFAULT_PASSWORD},
    )
    assert required.status_code == 401
    assert required.json()["detail"]["code"] == "two_factor_required"

    login = client.post(
        "/api/auth/login",
        json={
            "email": "designer@example.com",
            "password": DEFAULT_PASSWORD,
            "otp": totp_code(secret),
        },
    )
    assert login.status_code == 200

    disabled = client.post(
        "/api/me/two-factor/disable",
        json={"code": totp_code(secret)},
    )
    assert disabled.status_code == 200
    assert disabled.json()["user"]["two_factor_enabled"] is False
