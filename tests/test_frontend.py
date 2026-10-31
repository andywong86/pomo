"""Exercise browser Python with a strict stand-in for the JS object boundary.

This catches Python dicts passed to Vue; it does not replace a browser smoke test.
"""

import json
import re
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from pomo.app import create_app


class JSArray(list[Any]):
    def push(self, value: Any) -> None:
        self.append(value)


@pytest.fixture
def frontend(monkeypatch: pytest.MonkeyPatch) -> Any:
    state: Any = None
    exposed: Any = None
    mounted: Any = None

    def reactive(value: Any) -> Any:
        nonlocal state
        assert isinstance(value, SimpleNamespace), "Vue needs a native JS object"
        state = value
        return value

    def on_mounted(callback: Any) -> None:
        nonlocal mounted
        mounted = callback

    def create_app_stub(options: Any) -> Any:
        nonlocal exposed
        assert isinstance(options, SimpleNamespace), "App options must be a JS object"
        # Vue calls setup(props, context), not setup().
        exposed = options.setup(SimpleNamespace(), SimpleNamespace())
        return SimpleNamespace(mount=lambda selector: None)

    request = Mock()
    window = SimpleNamespace(
        document=SimpleNamespace(title="TODO.md · pomo"),
        Date=SimpleNamespace(now=Mock(return_value=0)),
        setInterval=Mock(return_value=1),
        clearInterval=Mock(),
        AudioContext=SimpleNamespace(new=Mock(return_value=Mock())),
        JSON=SimpleNamespace(
            parse=lambda value: json.loads(
                value, object_hook=lambda obj: SimpleNamespace(**obj)
            )
        ),
        Object=SimpleNamespace(new=SimpleNamespace),
        Array=SimpleNamespace(new=JSArray),
        Vue=SimpleNamespace(
            reactive=reactive,
            onMounted=on_mounted,
            toRefs=lambda value: SimpleNamespace(**vars(value)),
            computed=lambda callback: callback,
            createApp=create_app_stub,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "browser",
        SimpleNamespace(window=window, ajax=SimpleNamespace(ajax=lambda: request)),
    )
    html = create_app().test_client().get("/").get_data(as_text=True)
    script = re.search(r'<script type="text/python">(.*?)</script>', html, re.DOTALL)
    assert script is not None
    # Execute only our own template's Python, never user-provided content.
    exec(compile(script.group(1), "<browser-python>", "exec"), {})  # noqa: S102

    return SimpleNamespace(
        state=state, exposed=exposed, window=window, mounted=mounted, request=request
    )


def test_vue_bridge_and_callbacks(frontend: Any) -> None:
    state, exposed = frontend.state, frontend.exposed
    mounted, request = frontend.mounted, frontend.request
    assert state.tasks == []
    # Vue computed getters receive the previous computed value.
    assert exposed.completed(None) == 0
    assert exposed.filtered(None) == []
    mounted()
    request.open.assert_called_once_with("GET", "/api/todos", True)
    assert state.loading is True
    received = request.bind.call_args.args[1]
    received(
        SimpleNamespace(
            status=200,
            text=json.dumps(
                {
                    "content": "- [ ] Plan day\n- [x] Coffee\n",
                    "revision": "revision-1",
                    "tasks": [
                        {"text": "Plan day", "done": False, "line": 1, "indent": 2},
                        {"text": "Coffee", "done": True, "line": 2, "indent": 0},
                    ],
                }
            ),
        )
    )
    assert state.loading is False
    assert exposed.completed(0) == 1
    assert len(exposed.filtered(JSArray())) == 2
    state.status = "open"
    assert [task.text for task in exposed.filtered()] == ["Plan day"]
    assert exposed.filtered()[0].indent == 2
    state.status = "done"
    assert [task.text for task in exposed.filtered()] == ["Coffee"]
    exposed.edit()
    assert state.editing is True
    assert state.draft == state.content
    state.draft = "- [ ] Changed\n"
    exposed.save()
    assert request.open.call_args.args == ("PUT", "/api/todos", True)
    assert json.loads(request.send.call_args.args[0]) == {
        "content": "- [ ] Changed\n",
        "revision": "revision-1",
    }
    request.set_header.assert_any_call("Content-Type", "application/json")
    received(SimpleNamespace(status=409, text='{"error": "File changed"}'))
    assert state.editing is True
    assert state.draft == "- [ ] Changed\n"
    exposed.cancel()
    assert state.editing is False
    state.query = "missing"
    assert exposed.filtered() == []
    received(SimpleNamespace(status=404, text='{"error": "File missing"}'))
    assert state.error == "File missing"
    received(SimpleNamespace(status=0, text=""))
    assert "connection" in state.error


@pytest.mark.parametrize(
    ("minutes", "seconds", "display"),
    [
        (1, 60, "01:00"),
        (17, 1020, "17:00"),
        (60, 3600, "60:00"),
        (0, 60, "01:00"),
        (90, 3600, "60:00"),
    ],
)
def test_timer_duration(
    frontend: Any, minutes: int, seconds: int, display: str
) -> None:
    frontend.exposed.set_minutes(minutes)
    assert frontend.state.duration == seconds
    assert frontend.state.remaining == seconds
    assert frontend.exposed.timer_display(None) == display
    assert frontend.state.running is False


def test_timer_pause_resume(frontend: Any) -> None:
    state, exposed, window = frontend.state, frontend.exposed, frontend.window
    exposed.start_timer()
    assert state.running is True
    window.setInterval.assert_called_once()
    exposed.start_timer()
    window.setInterval.assert_called_once()  # Repeated starts cannot add intervals.
    tick = window.setInterval.call_args.args[0]
    window.Date.now.return_value = 61_250
    tick()
    assert state.remaining == 1439
    assert exposed.timer_display() == "23:59"
    assert "23:59" in window.document.title
    exposed.pause_timer()
    assert state.running is False
    window.clearInterval.assert_called_with(1)
    window.Date.now.return_value = 120_000
    exposed.start_timer()
    assert state.remaining == 1439
    window.Date.now.return_value = 121_000
    tick()
    assert state.remaining == 1438
    exposed.pause_timer()
    assert state.remaining == 1438
    assert state.running is False


def test_timer_completion_after_delayed_callback(frontend: Any) -> None:
    state, exposed, window = frontend.state, frontend.exposed, frontend.window
    exposed.start_timer()
    tick = window.setInterval.call_args.args[0]
    # Background tabs may delay callbacks: elapsed time, not tick count, matters.
    window.Date.now.return_value = 1_700_000
    tick()
    assert state.remaining == 0
    assert state.running is False
    assert not hasattr(state, "sessions")
    assert "finished" in state.timer_message
    assert "Time's up!" in window.document.title
    window.AudioContext.new.return_value.createOscillator.assert_called_once()
    exposed.toggle_timer()
    assert state.remaining == 0  # Completion cannot implicitly restore a duration.
    assert state.running is False
    exposed.set_minutes(12)
    exposed.toggle_timer()
    assert state.remaining == 720
    assert state.running is True
    assert state.timer_message == ""


def test_changing_duration_stops_timer(frontend: Any) -> None:
    state, exposed, window = frontend.state, frontend.exposed, frontend.window
    exposed.start_timer()
    exposed.set_minutes(7)
    assert state.running is False
    assert state.remaining == 420
    window.clearInterval.assert_called_with(1)
    exposed.start_timer()
    window.Date.now.return_value = 420_000
    tick = window.setInterval.call_args.args[0]
    tick()
    assert state.remaining == 0
    assert "Timer finished" in state.timer_message
    tick()  # A queued callback after clearing must not repeat the alert.
    window.AudioContext.new.return_value.createOscillator.assert_called_once()
    exposed.set_minutes(9)
    assert state.remaining == 540
    assert state.running is False


def test_timer_works_without_audio(frontend: Any) -> None:
    frontend.window.AudioContext.new.side_effect = RuntimeError("Audio unavailable")
    frontend.exposed.start_timer()
    frontend.window.Date.now.return_value = 1_500_000
    frontend.window.setInterval.call_args.args[0]()
    assert frontend.state.remaining == 0
    assert frontend.state.running is False


def dial_event(x: float, y: float, size: float = 200) -> Any:
    bounds = SimpleNamespace(left=100, top=50, width=size, height=size)
    return SimpleNamespace(
        clientX=100 + x * size,
        clientY=50 + y * size,
        currentTarget=SimpleNamespace(getBoundingClientRect=lambda: bounds),
    )


@pytest.mark.parametrize(
    ("x", "y", "minutes"),
    [
        (0.5, 0, 60),
        (1, 0.5, 45),
        (0.5, 1, 30),
        (0, 0.5, 15),
        (0.51, 0.05, 60),
        (0.49, 0.05, 1),
    ],
)
@pytest.mark.parametrize("size", [200, 320])
def test_dial_click_selects_minutes(
    frontend: Any, x: float, y: float, minutes: int, size: float
) -> None:
    frontend.exposed.select_time(dial_event(x, y, size))
    assert frontend.state.duration == minutes * 60
    assert frontend.state.remaining == minutes * 60
    assert frontend.state.running is False


@pytest.mark.parametrize(("x", "y"), [(0.5, 0.5), (0, 0), (1, 1)])
def test_dial_ignores_center_and_outside(frontend: Any, x: float, y: float) -> None:
    frontend.exposed.start_timer()
    frontend.exposed.select_time(dial_event(x, y))
    assert frontend.state.duration == 1500
    assert frontend.state.running is True


def test_dial_click_pauses_running_timer(frontend: Any) -> None:
    frontend.exposed.start_timer()
    frontend.exposed.select_time(dial_event(0, 0.5))
    assert frontend.state.remaining == 900
    assert frontend.state.running is False
    frontend.window.clearInterval.assert_called_once_with(1)


@pytest.mark.parametrize(
    ("key", "minutes"),
    [
        ("ArrowUp", 26),
        ("ArrowRight", 26),
        ("ArrowDown", 24),
        ("ArrowLeft", 24),
        ("Home", 1),
        ("End", 60),
    ],
)
def test_dial_keyboard(frontend: Any, key: str, minutes: int) -> None:
    event = SimpleNamespace(key=key, preventDefault=Mock())
    frontend.exposed.dial_key(event)
    assert frontend.state.duration == minutes * 60
    event.preventDefault.assert_called_once()


def test_dial_keyboard_limits_and_unhandled_keys(frontend: Any) -> None:
    frontend.exposed.set_minutes(60)
    frontend.exposed.dial_key(SimpleNamespace(key="ArrowUp", preventDefault=Mock()))
    assert frontend.state.duration == 3600
    frontend.exposed.set_minutes(1)
    frontend.exposed.dial_key(SimpleNamespace(key="ArrowDown", preventDefault=Mock()))
    assert frontend.state.duration == 60
    event = SimpleNamespace(key="Tab", preventDefault=Mock())
    frontend.exposed.dial_key(event)
    event.preventDefault.assert_not_called()


def test_visual_sector_uses_fixed_60_minute_scale() -> None:
    html = create_app().test_client().get("/").get_data(as_text=True)
    assert "(remaining / 10) + 'deg'" in html  # 3600 seconds = 360 degrees.
    assert 'aria-valuemax="60"' in html
    assert 'role="slider"' in html
    assert "set_mode" not in html
    assert "timers complete this visit" not in html
    assert "sessions" not in html
    assert "timer-readout" not in html
    assert "timer-help" not in html
    assert "Select a duration, then start." not in html
    assert 'v-if="timer_message" class="timer-status"' in html
    assert "reset_timer" not in html
    assert ">Reset</button>" not in html
    assert '@click.stop="toggle_timer"' in html
    assert 'class="timer-hub"' in html
    assert "aria-label=\"running ? 'Pause timer' : 'Start or resume timer'\"" in html


def test_five_minute_labels_match_anticlockwise_click_scale(frontend: Any) -> None:
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)
    labels = re.findall(
        r'<span class="dial-label" style="left: ([\d.]+)%; top: ([\d.]+)%" '
        r'aria-hidden="true">(\d+)</span>',
        html,
    )
    assert [int(minute) for _, _, minute in labels] == list(range(5, 61, 5))
    for left, top, minute in labels:
        frontend.exposed.select_time(dial_event(float(left) / 100, float(top) / 100))
        assert frontend.state.duration == int(minute) * 60
    css = client.get("/static/styles.css").get_data(as_text=True)
    assert ".timer-sector {\n  transform: scaleX(-1);" in css


def test_center_toggles_without_changing_duration(frontend: Any) -> None:
    state, exposed, window = frontend.state, frontend.exposed, frontend.window
    exposed.toggle_timer()
    assert state.running is True
    window.Date.now.return_value = 90_000
    exposed.toggle_timer()
    assert state.running is False
    assert state.remaining == 1410
    assert state.duration == 1500
    window.Date.now.return_value = 180_000
    exposed.toggle_timer()
    assert state.running is True
    assert state.remaining == 1410
    assert state.duration == 1500
    assert not hasattr(exposed, "reset_timer")


def test_knob_spins_while_running_without_flashing_slice() -> None:
    client = create_app().test_client()
    html = client.get("/").get_data(as_text=True)
    assert 'class="timer-hub" :class="{ \'is-running\': running }"' in html
    assert '<div class="timer-sector" aria-hidden="true"></div>' in html
    css = client.get("/static/styles.css").get_data(as_text=True)
    assert "timer-breathe" not in css
    assert ".timer-sector.is-running" not in css
    assert ".timer-hub.is-running::after {" in css
    assert "animation: knob-spin 2.5s linear infinite;" in css
    assert "pointer-events: none;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".timer-hub.is-running::after { animation: none; }" in css
