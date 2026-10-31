import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from pomo.app import create_app


def edit_headers(client: FlaskClient) -> dict[str, str]:
    html = client.get("/").get_data(as_text=True)
    match = re.search(r'csrf_token = ("[^"]+")', html)
    assert match is not None
    return {"X-Pomo-Token": json.loads(match.group(1))}


def test_save_preserves_markdown_and_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "TODO.md"
    original = b"# Today\r\n\r\n- [ ] Task\r\nNotes\r\n"
    path.write_bytes(original)
    path.chmod(0o640)
    client = create_app(tmp_path).test_client()
    payload = client.get("/api/todos").get_json()
    assert payload["content"].encode() == original
    changed = "# Today\r\n\r\n- [x] Updated ✓\r\nNotes\r\n- [ ] New\r\n"
    response = client.put(
        "/api/todos",
        headers=edit_headers(client),
        json={
            "content": changed,
            "revision": payload["revision"],
        },
    )
    assert response.status_code == 200
    assert path.read_bytes() == changed.encode()
    assert path.stat().st_mode & 0o777 == 0o640
    assert response.get_json()["tasks"][0]["done"] is True
    assert response.get_json()["revision"] != payload["revision"]
    assert response.get_json() == client.get("/api/todos").get_json()
    assert list(tmp_path.iterdir()) == [path]


def test_reject_stale_save(tmp_path: Path) -> None:
    path = tmp_path / "TODO.md"
    path.write_text("- [ ] First")
    client = create_app(tmp_path).test_client()
    revision = client.get("/api/todos").get_json()["revision"]
    path.write_text("- [ ] External change")
    response = client.put(
        "/api/todos",
        headers=edit_headers(client),
        json={
            "content": "Overwrite",
            "revision": revision,
        },
    )
    assert response.status_code == 409
    assert path.read_text() == "- [ ] External change"


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"content": 1, "revision": "x"}, {"content": "x"}]
)
def test_reject_invalid_payload(tmp_path: Path, payload: object) -> None:
    client = create_app(tmp_path).test_client()
    response = client.put("/api/todos", headers=edit_headers(client), json=payload)
    assert response.status_code == 400
    assert not (tmp_path / "TODO.md").exists()


def test_require_edit_token(tmp_path: Path) -> None:
    path = tmp_path / "TODO.md"
    path.write_text("Original")
    client = create_app(tmp_path).test_client()
    for headers in ({}, {"X-Pomo-Token": "wrong"}):
        assert (
            client.put(
                "/api/todos",
                headers=headers,
                json={
                    "content": "Overwrite",
                    "revision": "x",
                },
            ).status_code
            == 403
        )
    assert path.read_text() == "Original"


def test_failed_save_leaves_original_intact(tmp_path: Path) -> None:
    path = tmp_path / "TODO.md"
    path.write_text("Original")
    client = create_app(tmp_path).test_client()
    revision = client.get("/api/todos").get_json()["revision"]
    headers = edit_headers(client)
    with patch("pomo.app.Path.replace", side_effect=PermissionError):
        response = client.put(
            "/api/todos",
            headers=headers,
            json={
                "content": "Changed",
                "revision": revision,
            },
        )
    assert response.status_code == 422
    assert path.read_text() == "Original"
    assert list(tmp_path.iterdir()) == [path]


def test_cannot_create_missing_file(tmp_path: Path) -> None:
    client = create_app(tmp_path).test_client()
    response = client.put(
        "/api/todos",
        headers=edit_headers(client),
        json={
            "content": "New",
            "revision": "x",
        },
    )
    assert response.status_code == 404
    assert not (tmp_path / "TODO.md").exists()
