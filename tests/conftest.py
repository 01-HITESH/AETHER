from __future__ import annotations

from io import BytesIO
from pathlib import Path
import time
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from BACKEND.config import Settings
from BACKEND.main import create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PASSWORD = "correct-horse-123"


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    environment = {
        "AETHER_DATA_DIR": str(data_dir),
        "AETHER_DB_PATH": str(data_dir / "database" / "aether.sqlite3"),
        "AETHER_SECRET_KEY": "test-secret-key",
        "AETHER_ENV": "testing",
        "AETHER_COOKIE_SECURE": "false",
        "AETHER_GENERATION_PROVIDER": "local_demo",
        "AETHER_GENERATION_MODEL": "local-demo-v2",
        "AETHER_GENERATION_VARIANTS": "3",
        "AETHER_MAX_UPLOAD_BYTES": str(64 * 1024),
        "AETHER_MAX_PROFILE_IMAGE_BYTES": str(64 * 1024),
        "AETHER_RATE_LIMIT_ENABLED": "false",
        "COMFYUI_WORKFLOW_PATH": "",
        "AETHER_CLOUD_GENERATION_URL": "",
        "AETHER_CLOUD_GENERATION_API_KEY": "",
        "GOOGLE_CLIENT_IDS": "",
        "GOOGLE_CLIENT_ID": "",
        "AETHER_SMTP_HOST": "",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_env(PROJECT_ROOT)
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def register_user() -> Callable:
    def register(
        client: TestClient,
        *,
        email: str = "designer@example.com",
        password: str = DEFAULT_PASSWORD,
        name: str = "Test Designer",
    ):
        response = client.post(
            "/api/auth/register",
            json={"name": name, "email": email, "password": password},
        )
        assert response.status_code == 201, response.text
        return response

    return register


@pytest.fixture
def room_image() -> Callable:
    def make_image(
        width: int = 640,
        height: int = 420,
        color: str = "#aab8ae",
        image_format: str = "JPEG",
    ) -> bytes:
        output = BytesIO()
        Image.new("RGB", (width, height), color).save(output, image_format)
        return output.getvalue()

    return make_image


@pytest.fixture
def upload_room(room_image: Callable) -> Callable:
    def upload(
        client: TestClient,
        *,
        filename: str = "room.jpg",
        content_type: str = "image/jpeg",
        data: bytes | None = None,
    ) -> dict:
        response = client.post(
            "/api/uploads",
            files={"file": (filename, data or room_image(), content_type)},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return upload


@pytest.fixture
def wait_for_job() -> Callable:
    def wait(
        client: TestClient,
        job_id: str,
        states: set[str] | None = None,
        timeout: float = 20,
    ) -> dict:
        terminal_states = states or {"completed", "failed", "cancelled"}
        deadline = time.monotonic() + timeout
        last_job: dict | None = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/generation/jobs/{job_id}")
            assert response.status_code == 200, response.text
            last_job = response.json()["job"]
            if last_job["state"] in terminal_states:
                return last_job
            time.sleep(0.05)
        pytest.fail(f"Job {job_id} did not reach {terminal_states}; last value: {last_job}")

    return wait
