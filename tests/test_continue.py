from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError, TimerAlreadyRunning


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_continue_uses_the_most_recent_project(app):
    app.add_project("writing")
    app.add_project("reading")
    app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0))
    app.log("reading", utc(2026, 10, 20, 11, 0), utc(2026, 10, 20, 11, 30))
    entry = app.continue_latest(note="next chapter", tags=["draft"], at=utc(2026, 10, 20, 12, 0))
    assert entry.project == "reading"
    assert entry.note == "next chapter"
    assert entry.tags == ("draft",)
    assert entry.ended_at is None


def test_continue_without_history(app):
    with pytest.raises(DaymarkError, match="No entries yet"):
        app.continue_latest()


def test_continue_refuses_an_archived_project(app):
    app.add_project("writing")
    app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0))
    app.archive_project("writing")
    with pytest.raises(DaymarkError, match="archived"):
        app.continue_latest(at=utc(2026, 10, 20, 12, 0))


def test_continue_refuses_a_second_timer(app):
    app.add_project("writing")
    app.start("writing", at=utc(2026, 10, 20, 9, 0))
    with pytest.raises(TimerAlreadyRunning):
        app.continue_latest()


def test_continue_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert (
        main(
            [
                "log",
                "writing",
                "--start",
                "2026-10-20 09:00",
                "--duration",
                "20m",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["continue", "--note", "more"]) == 0
    out = capsys.readouterr().out
    assert "Continued writing" in out
    assert "more" in out
