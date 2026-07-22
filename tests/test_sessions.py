from __future__ import annotations

from fastapi.testclient import TestClient
from tests.conftest import DEFAULT_PASSWORD


def test_session_management(app, client, register_user):
    register_user(client, email="session.test@example.com")

    # Log in from a second client
    secondary = TestClient(app)
    try:
        login_sec = secondary.post(
            "/api/auth/login",
            json={"email": "session.test@example.com", "password": DEFAULT_PASSWORD},
        )
        assert login_sec.status_code == 200

        # List active sessions from primary client
        res = client.get("/api/me/sessions")
        assert res.status_code == 200
        sessions = res.json()["sessions"]
        assert len(sessions) == 2

        current_session = next(s for s in sessions if s["current"])
        other_session = next(s for s in sessions if not s["current"])

        # Attempt to revoke current session via delete endpoint (should be blocked)
        bad_revoke = client.delete(f"/api/me/sessions/{current_session['id']}")
        assert bad_revoke.status_code == 400

        # Revoke the secondary session
        good_revoke = client.delete(f"/api/me/sessions/{other_session['id']}")
        assert good_revoke.status_code == 200

        # Secondary client is now logged out / unauthorized
        assert secondary.get("/api/me").status_code == 401
    finally:
        secondary.close()
