from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from pomo.app import create_app, main, parse_todos


def test_parse_todos() -> None:
    assert parse_todos(
        "# Today\n- [ ] Open\n  * [x] Done\n+ [X] Also done\n"
        "1. [ ] Numbered\n2) [ ] Another\nordinary text\n- no checkbox\n"
    ) == [
        {"line": 2, "text": "Open", "done": False, "indent": 0},
        {"line": 3, "text": "Done", "done": True, "indent": 2},
        {"line": 4, "text": "Also done", "done": True, "indent": 0},
        {"line": 5, "text": "Numbered", "done": False, "indent": 0},
        {"line": 6, "text": "Another", "done": False, "indent": 0},
    ]


def test_ignore_fenced_examples() -> None:
    content = (
        "```markdown\n- [ ] Example\n~~~\n- [ ] Still fenced\n```\n"
        "~~~~\n- [ ] Another example\n~~~\n- [ ] Still fenced\n~~~~\n"
        "- [ ] Real task\n"
    )
    assert parse_todos(content) == [
        {"line": 11, "text": "Real task", "done": False, "indent": 0}
    ]


def test_index(tmp_path: Path) -> None:
    response = create_app(tmp_path).test_client().get("/")
    assert response.status_code == 200
    assert b"TODO.md" in response.data
    assert b"/static/vendor/vue-3.5.13/vue.global.prod.js" in response.data
    assert b'type="text/python"' in response.data
    assert b"{{ task.text }}" in response.data


def test_scripts_are_served_locally(tmp_path: Path) -> None:
    from html.parser import HTMLParser

    class ScriptParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.sources: list[str] = []

        def handle_starttag(
            self, tag: str, attrs: list[tuple[str, str | None]]
        ) -> None:
            if tag == "script":
                self.sources.extend(
                    value for key, value in attrs if key == "src" and value
                )

    client = create_app(tmp_path).test_client()
    parser = ScriptParser()
    parser.feed(client.get("/").get_data(as_text=True))
    assert parser.sources == [
        "/static/vendor/vue-3.5.13/vue.global.prod.js",
        "/static/vendor/brython-3.15.0/brython.min.js",
        "/static/vendor/brython-3.15.0/brython_stdlib.js",
    ]
    for source in parser.sources:
        response = client.get(source)
        assert response.status_code == 200
        assert response.mimetype is not None
        assert "javascript" in response.mimetype
        assert len(response.data) > 100_000


def test_reads_and_refreshes_selected_file(tmp_path: Path) -> None:
    path = tmp_path / "todo.md"
    path.write_text("- [ ] First", encoding="utf-8")
    client = create_app(tmp_path, "todo.md").test_client()
    response = client.get("/api/todos")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json == {
        "filename": "todo.md",
        "content": "- [ ] First",
        "revision": sha256(b"- [ ] First").hexdigest(),
        "tasks": [{"line": 1, "text": "First", "done": False, "indent": 0}],
    }
    path.write_text("- [x] Changed ✓", encoding="utf-8")
    assert client.get("/api/todos").get_json()["tasks"] == [
        {"line": 1, "text": "Changed ✓", "done": True, "indent": 0}
    ]


def test_defaults_to_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "TODO.md").write_text("- [ ] Local", encoding="utf-8")
    assert (
        create_app().test_client().get("/api/todos").get_json()["tasks"][0]["text"]
        == "Local"
    )


def test_missing_file(tmp_path: Path) -> None:
    response = create_app(tmp_path).test_client().get("/api/todos")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]
    assert not (tmp_path / "TODO.md").exists()


@pytest.mark.parametrize("content", ["", "# No tasks\n", "just text"])
def test_empty_list(tmp_path: Path, content: str) -> None:
    (tmp_path / "TODO.md").write_text(content, encoding="utf-8")
    assert (
        create_app(tmp_path).test_client().get("/api/todos").get_json()["tasks"] == []
    )


def test_unreadable_file(tmp_path: Path) -> None:
    (tmp_path / "TODO.md").write_bytes(b"\xff")
    assert create_app(tmp_path).test_client().get("/api/todos").status_code == 422


def test_browser_cannot_select_files(tmp_path: Path) -> None:
    (tmp_path / "TODO.md").write_text("- [ ] Public", encoding="utf-8")
    (tmp_path / "secret.md").write_text("- [ ] Secret", encoding="utf-8")
    client = create_app(tmp_path).test_client()
    response = client.get("/api/todos?file=secret.md")
    assert response.get_json()["tasks"][0]["text"] == "Public"
    assert client.get("/secret.md").status_code == 404
    assert client.post("/api/todos").status_code == 405


def test_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["pomo", str(tmp_path), "--file", "tasks.md", "--port", "5050"]
    )
    with patch("pomo.app.Flask.run") as run:
        main()
    run.assert_called_once_with(host="127.0.0.1", port=5050)


def test_cli_rejects_invalid_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["pomo", str(tmp_path / "missing")])
    with pytest.raises(SystemExit, match="2"):
        main()
