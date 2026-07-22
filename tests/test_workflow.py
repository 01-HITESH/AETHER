from __future__ import annotations

from io import BytesIO
import json
import zipfile

from fastapi.testclient import TestClient


def test_upload_to_result_export_and_protected_share_workflow(
    app,
    client,
    register_user,
    upload_room,
    wait_for_job,
):
    register_user(client, email="flow@example.com", name="Flow Designer")
    upload = upload_room(client)

    queued = client.post(
        "/api/generation/jobs",
        json={
            "uploadId": upload["uploadId"],
            "roomType": "living_room",
            "style": "modern",
            "provider": "local_demo",
            "model": "local-demo-v2",
            "variantCount": 3,
            "seeds": [11, 22, 33],
            "requirements": {"notes": "Oak surfaces and green textiles."},
            "settings": {
                "room_width_m": 6.2,
                "room_depth_m": 4.8,
                "room_height_m": 3.1,
            },
        },
    )
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["job"]["id"]

    job = wait_for_job(client, job_id, {"completed"})
    assert job["progress"] == 100
    assert job["provider"] == "local_demo"
    assert job["seeds"] == [11, 22, 33]
    assert len(job["alternatives"]) == 3

    first = job["alternatives"][0]
    assert first["seed"] == 11
    assert first["metadata"]["provider"] == "local_demo"
    for media_key in ("source_url", "redesign_url", "pano_url", "thumb_url"):
        response = client.get(first[media_key])
        assert response.status_code == 200, (media_key, response.text)
        assert response.headers["content-type"].startswith("image/")

    tours = client.get("/api/tours")
    assert tours.status_code == 200
    assert len(tours.json()["tours"]) == 3

    saved = client.post(f"/api/tours/{first['id']}/save")
    favorited = client.post(f"/api/tours/{first['id']}/favorite")
    assert saved.status_code == 200
    assert favorited.status_code == 200
    assert saved.json()["tour"]["saved"] is True
    assert favorited.json()["tour"]["favorite"] is True

    account = client.get("/api/me").json()
    assert account["stats"] == {"projects": 3, "saved": 1, "favorites": 1}

    model_export = client.get(f"/api/tours/{first['id']}/export/model")
    assert model_export.status_code == 200
    assert model_export.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(model_export.content)) as package:
        assert set(package.namelist()) == {
            "manifest.json",
            "room.mtl",
            "room.obj",
            "texture.jpg",
        }
        manifest = json.loads(package.read("manifest.json"))
        assert manifest["format"] == "Wavefront OBJ package"
        assert manifest["dimensions"] == {
            "width": 6.2,
            "depth": 4.8,
            "height": 3.1,
        }

    report = client.get(f"/api/tours/{first['id']}/export/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert b"AETHER generation report" in report.content

    anonymous = TestClient(app)
    try:
        assert anonymous.get(first["redesign_url"]).status_code == 401
        assert anonymous.get(f"/api/tours/{first['id']}/export/model").status_code == 401
    finally:
        anonymous.close()

    share_response = client.post(
        f"/api/tours/{first['id']}/shares",
        json={"expiresHours": 24, "password": "room-pass"},
    )
    assert share_response.status_code == 201
    share = share_response.json()["share"]
    token = share["token"]
    assert share["password_protected"] is True

    assert client.get(f"/api/shares/{token}").status_code == 401
    assert client.post(
        f"/api/shares/{token}",
        json={"password": "wrong-pass"},
    ).status_code == 401
    opened = client.post(
        f"/api/shares/{token}",
        json={"password": "room-pass"},
    )
    assert opened.status_code == 200
    assert opened.json()["tour"]["id"] == first["id"]

    shared_media_url = f"/api/shares/{token}/media/redesign"
    assert client.get(shared_media_url).status_code == 401
    shared_media = client.get(
        shared_media_url,
        headers={"X-Share-Password": "room-pass"},
    )
    assert shared_media.status_code == 200
    assert shared_media.headers["cache-control"] == "private, no-store"

    deleted = client.delete(f"/api/tours/{first['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/tours/{first['id']}").status_code == 404
    assert client.get(first["redesign_url"]).status_code == 404
    assert client.post(
        f"/api/shares/{token}",
        json={"password": "room-pass"},
    ).status_code == 404
