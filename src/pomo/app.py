"""Local viewer and editor for Markdown todo lists."""

import argparse
import re
import secrets
import stat
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from flask import Flask, Response, jsonify, render_template, request

TASK = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+\[([ xX])\]\s+(.+?)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def parse_todos(content: str) -> list[dict[str, str | int | bool]]:
    """Extract Markdown tasks, preserving order and source line numbers."""
    tasks: list[dict[str, str | int | bool]] = []
    fence_character = ""
    fence_length = 0
    for line_number, line in enumerate(content.splitlines(), start=1):
        fence = FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not fence_character:
                fence_character, fence_length = marker[0], len(marker)
            elif (
                marker[0] == fence_character
                and len(marker) >= fence_length
                and not line[fence.end() :].strip()
            ):
                fence_character = ""
            continue
        if fence_character:
            continue
        match = TASK.match(line)
        if match:
            tasks.append(
                {
                    "line": line_number,
                    "text": match.group(2),
                    "done": match.group(1).lower() == "x",
                    "indent": len(line.expandtabs(4))
                    - len(line.expandtabs(4).lstrip(" ")),
                }
            )
    return tasks


def create_app(folder: Path | None = None, filename: str = "TODO.md") -> Flask:
    """Bind one todo file at startup; browsers cannot choose filesystem paths."""
    app = Flask(__name__)
    todo_path = ((folder or Path.cwd()) / filename).resolve()
    csrf_token = secrets.token_urlsafe(32)
    write_lock = Lock()
    app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
    app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1", "[::1]"]

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html", filename=todo_path.name, csrf_token=csrf_token
        )

    @app.route("/api/todos", methods=["GET", "PUT"])
    def todos() -> tuple[Response, int]:
        if request.method == "PUT":
            if not secrets.compare_digest(
                request.headers.get("X-Pomo-Token", "").encode(), csrf_token.encode()
            ):
                return jsonify(error="Invalid edit token. Reload this page."), 403
            payload = request.get_json(silent=True)
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("content"), str)
                or not isinstance(payload.get("revision"), str)
            ):
                return jsonify(error="Expected content and revision strings."), 400
        else:
            payload = None
        with write_lock:
            try:
                raw = todo_path.read_bytes()
                content = raw.decode("utf-8")
                if payload is not None:
                    if payload["revision"] != sha256(raw).hexdigest():
                        return jsonify(
                            error="File changed on disk. Copy your edits, cancel, then refresh."
                        ), 409
                    raw = payload["content"].encode("utf-8")
                    mode = stat.S_IMODE(todo_path.stat().st_mode)
                    temporary: Path | None = None
                    try:
                        with NamedTemporaryFile(
                            dir=todo_path.parent, delete=False
                        ) as file:
                            temporary = Path(file.name)
                            file.write(raw)
                        temporary.chmod(mode)
                        temporary.replace(todo_path)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                    content = payload["content"]
            except FileNotFoundError:
                return jsonify(error=f"Todo file not found: {todo_path.name}"), 404
            except (OSError, UnicodeError):
                return jsonify(
                    error="Could not read or save todo file as UTF-8 text."
                ), 422
        response = jsonify(
            filename=todo_path.name,
            tasks=parse_todos(content),
            content=content,
            revision=sha256(raw).hexdigest(),
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument(
        "--file", default="TODO.md", help="Todo filename (default: TODO.md)"
    )
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error(f"Not a directory: {args.folder}")
    create_app(args.folder, args.file).run(host="127.0.0.1", port=args.port)
