from __future__ import annotations

from tests.conftest import DEFAULT_PASSWORD


def test_password_reset_flow(app, client, register_user):
    register_user(client, email="reset.user@example.com", password=DEFAULT_PASSWORD)

    # 1. Request reset for non-existing email (generic success message)
    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "nonexistent@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "development_reset_token" not in response.json()

    # 2. Request reset for existing email
    response = client.post(
        "/api/auth/password-reset/request",
        json={"email": "reset.user@example.com"},
    )
    assert response.status_code == 200
    token = response.json().get("development_reset_token")
    assert token, "Development reset token should be returned in testing environment"

    # 3. Try reset with invalid token
    invalid_confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "invalid-token-123", "newPassword": "new-password-123"},
    )
    assert invalid_confirm.status_code == 400

    # 4. Confirm reset with valid token
    confirm = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "newPassword": "new-password-123"},
    )
    assert confirm.status_code == 200
    assert confirm.json() == {"ok": True}

    # 5. Old password fails
    old_login = client.post(
        "/api/auth/login",
        json={"email": "reset.user@example.com", "password": DEFAULT_PASSWORD},
    )
    assert old_login.status_code == 401

    # 6. New password succeeds
    new_login = client.post(
        "/api/auth/login",
        json={"email": "reset.user@example.com", "password": "new-password-123"},
    )
    assert new_login.status_code == 200
