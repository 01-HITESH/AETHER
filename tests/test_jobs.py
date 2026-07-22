from __future__ import annotations

import threading
import time

from BACKEND.providers.base import GenerationProvider, ProviderError
from BACKEND.providers.local_demo import LocalDemoProvider


class FailOnceProvider(GenerationProvider):
    name = "local_demo"
    display_name = "Fail once provider"

    def __init__(self):
        self.calls = 0
        self.delegate = LocalDemoProvider()

    def generate(self, request, progress, cancelled):
        self.calls += 1
        if self.calls == 1:
            progress(20, "Simulated provider failure")
            raise ProviderError("Temporary provider failure.")
        return self.delegate.generate(request, progress, cancelled)


class BlockingProvider(GenerationProvider):
    name = "local_demo"
    display_name = "Blocking provider"

    def __init__(self):
        self.started = threading.Event()

    def generate(self, request, progress, cancelled):
        progress(10, "Waiting for cancellation")
        self.started.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.ensure_not_cancelled(cancelled)
            time.sleep(0.02)
        raise ProviderError("Cancellation did not arrive.")


def create_one_variant_job(client, upload_id: str) -> str:
    response = client.post(
        "/api/generation/jobs",
        json={
            "uploadId": upload_id,
            "roomType": "office",
            "style": "industrial",
            "provider": "local_demo",
            "variantCount": 1,
            "seeds": [7123],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["job"]["id"]


def test_failed_job_can_be_retried(
    app,
    client,
    register_user,
    upload_room,
    wait_for_job,
):
    register_user(client)
    upload = upload_room(client, data=None)
    provider = FailOnceProvider()
    app.state.generation.providers["local_demo"] = provider

    job_id = create_one_variant_job(client, upload["uploadId"])
    failed = wait_for_job(client, job_id, {"failed"})
    assert failed["error"] == "Temporary provider failure."
    assert failed["attempts"] == 1

    retry = client.post(f"/api/generation/jobs/{job_id}/retry")
    assert retry.status_code == 202
    completed = wait_for_job(client, job_id, {"completed"})
    assert completed["progress"] == 100
    assert completed["attempts"] == 2
    assert len(completed["alternatives"]) == 1
    assert provider.calls == 2


def test_running_job_can_be_cancelled(
    app,
    client,
    register_user,
    upload_room,
    wait_for_job,
):
    register_user(client)
    upload = upload_room(client, data=None)
    provider = BlockingProvider()
    app.state.generation.providers["local_demo"] = provider

    job_id = create_one_variant_job(client, upload["uploadId"])
    assert provider.started.wait(timeout=5)

    cancelled = client.post(f"/api/generation/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    final = wait_for_job(client, job_id, {"cancelled"})
    assert final["cancel_requested"] is True
    assert final["state"] == "cancelled"
