from __future__ import annotations

from io import BytesIO
import json
import zipfile


def test_export_security_and_formats(app, client, register_user, upload_room, wait_for_job):
    register_user(client, email="export.tester@example.com")
    upload = upload_room(client)

    # Create job to produce a tour design
    job_res = client.post(
        "/api/generation/jobs",
        json={
            "uploadId": upload["uploadId"],
            "roomType": "bedroom",
            "style": "scandinavian",
            "variantCount": 1,
            "seeds": [42],
            "settings": {"room_width_m": 4.5, "room_depth_m": 3.8, "room_height_m": 2.7},
        },
    )
    assert job_res.status_code == 202
    job = wait_for_job(client, job_res.json()["job"]["id"], {"completed"})
    tour_id = job["alternatives"][0]["id"]

    # 1. HTML Report export
    report = client.get(f"/api/tours/{tour_id}/export/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert b"Scandinavian Bedroom 1" in report.content

    # 2. 3D OBJ package zip export
    model = client.get(f"/api/tours/{tour_id}/export/model")
    assert model.status_code == 200
    assert model.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(model.content)) as archive:
        files = set(archive.namelist())
        assert "room.obj" in files
        assert "room.mtl" in files
        assert "manifest.json" in files
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["dimensions"] == {"width": 4.5, "depth": 3.8, "height": 2.7}

    # 3. Image export
    img = client.get(f"/api/tours/{tour_id}/export/hd")
    assert img.status_code == 200
    assert img.headers["content-type"].startswith("image/jpeg")

    # 4. Invalid export type returns 404
    invalid = client.get(f"/api/tours/{tour_id}/export/invalid_type")
    assert invalid.status_code == 404
