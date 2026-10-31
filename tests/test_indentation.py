from pathlib import Path

import pytest

from pomo.app import create_app, parse_todos


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "- [ ] Parent\n  - [ ] Child\n    - [x] Grandchild\n- [ ] Sibling",
            [0, 2, 4, 0],
        ),
        ("- [ ] Parent\n    - [ ] Child\n        - [ ] Grandchild", [0, 4, 8]),
        ("- [ ] Parent\n\t- [ ] Child\n\t\t- [ ] Grandchild", [0, 4, 8]),
        (
            "- [ ] Parent\n  1. [ ] Child\n    + [ ] Grandchild\n  * [ ] Sibling",
            [0, 2, 4, 2],
        ),
        (
            "- [ ] Parent\n\n  - [ ] Child\n  ```\n  - [ ] Example\n  ```\n- [ ] Next",
            [0, 2, 0],
        ),
    ],
)
def test_task_indentation(content: str, expected: list[int]) -> None:
    assert [task["indent"] for task in parse_todos(content)] == expected


def test_api_exposes_indentation_without_changing_source(tmp_path: Path) -> None:
    path = tmp_path / "TODO.md"
    content = "- [ ] Parent\n  - [x] Child\n    - [ ] Grandchild\n"
    path.write_text(content, encoding="utf-8")
    client = create_app(tmp_path).test_client()
    payload = client.get("/api/todos").get_json()
    assert [task["indent"] for task in payload["tasks"]] == [0, 2, 4]
    assert payload["content"] == content
    assert path.read_text(encoding="utf-8") == content
    assert b"'--indent': task.indent" in client.get("/").data
