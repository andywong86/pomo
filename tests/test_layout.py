from html.parser import HTMLParser

from pomo.app import create_app


class SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sections: list[str] = []
        self.top_level: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "section":
            name = dict(attrs).get("class") or ""
            if not self.sections:
                self.top_level.append(name)
            self.sections.append(name)

    def handle_endtag(self, tag: str) -> None:
        if tag == "section":
            self.sections.pop()


def test_timer_and_todos_are_separate_layout_panels() -> None:
    parser = SectionParser()
    parser.feed(create_app().test_client().get("/").get_data(as_text=True))
    assert parser.top_level == ["pomodoro", "todo-panel"]
    assert parser.sections == []
