from __future__ import annotations


def test_upload_validation(client, register_user):
    register_user(client)

    unsupported = client.post(
        "/api/uploads",
        files={"file": ("room.txt", b"not an image", "text/plain")},
    )
    assert unsupported.status_code == 400

    unreadable = client.post(
        "/api/uploads",
        files={"file": ("room.jpg", b"not a jpeg", "image/jpeg")},
    )
    assert unreadable.status_code == 400

    oversized = client.post(
        "/api/uploads",
        files={"file": ("large.jpg", b"x" * (64 * 1024 + 1), "image/jpeg")},
    )
    assert oversized.status_code == 413


def test_uploaded_media_requires_the_owner(client, register_user, upload_room):
    register_user(client, email="owner@example.com")
    upload = upload_room(client)
    media_url = upload["url"]

    owner_media = client.get(media_url)
    assert owner_media.status_code == 200
    assert owner_media.headers["content-type"].startswith("image/jpeg")
    assert owner_media.headers["cache-control"] == "private, max-age=300"

    client.cookies.clear()
    assert client.get(media_url).status_code == 401

    register_user(client, email="intruder@example.com")
    assert client.get(media_url).status_code == 404
