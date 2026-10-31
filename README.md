# pomo

Local todo viewer and editor. Flask serves one page; Vue renders it and Brython
handles loading, search, and filters in Python.

## Run

From this checkout:

```bash
uv run -- pomo                    # reads TODO.md in the current directory
uv run -- pomo /path/to/project   # reads that folder's TODO.md
uv run -- pomo . --file todo.md --port 5050
```

Open http://127.0.0.1:5000 (or your selected port). To launch from any folder,
install with `uv tool install /path/to/pomo`, then run `pomo`.

Create a UTF-8 `TODO.md`:

```markdown
# Today

- [ ] Plan the day
- [x] Make coffee
  - [ ] Review notes
```

Supports Markdown checkbox lists (`-`, `*`, `+`, or numbered markers).
Indent child tasks with spaces to show subtasks; deeper indentation appears
further right. Tabs count as four columns. Filters preserve task indentation.
Fenced code blocks are ignored. Task text is displayed literally, not rendered
as HTML. Click **Edit file** to edit Markdown, then **Save** or **Cancel**.
Edits can add, rename, complete, or remove tasks while preserving surrounding
Markdown. Saves replace the selected file atomically. If the file changed since
you loaded it, saving is rejected: copy your draft, cancel, and refresh first.
Missing or unreadable files show an error; missing files are not created.
Click **Refresh** to load edits made outside the app.

Server binds to localhost with debug mode off. Only the selected todo file is
exposed through the API; this is not a file browser. Writes require a page-specific
edit token, and requests are restricted to localhost hostnames. Keep this app local. Vue and Brython load from
pinned CDN URLs, so the browser needs internet access.

## Visual timer

A Time Timer-style disk sits in the left column beside todos on desktop and
stacks above them on narrow screens. Click the disk to select **1–60 minutes**,
rounded to whole minutes, increasing anti-clockwise: top = 60, left = 15,
bottom = 30, right = 45. Dial labels appear every five minutes.
The red sector always represents remaining time out of 60 minutes, so 15 minutes
fills a quarter disk and 60 minutes fills the whole disk.

Click the center **play** icon to start or resume, or its **pause** icon to pause
without changing remaining time. There is no Reset control. Selecting a duration
on the disk sets a new timer and leaves it paused. After completion, select
another duration to begin again. The center button also supports Enter/Space.
Focus the disk and use arrow keys to adjust by one minute, Home for 1 minute,
or End for 60 minutes.
Completion shows a message, updates the tab title, and plays a short tone when
browser audio is available. Sessions do not auto-start. Reloading clears the timer.

Countdown uses a deadline so delayed background-tab ticks do not accumulate
drift. Browsers may delay the completion sound while the tab or device sleeps.

## Development

```bash
uv run -- test
uv run -- typecheck
uv run -- lint
uv run -- format
uv run -- build
```
