from datetime import datetime, timedelta, timezone

import pytest

from daymark.cli import main
from daymark.errors import TimerAlreadyRunning
from daymark.store import BREAK_SECONDS, FOCUS_SECONDS


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_pomodoro_lengths_are_fixed():
    assert FOCUS_SECONDS == 25 * 60
    assert BREAK_SECONDS == 5 * 60


def test_pomodoro_start_is_a_local_focus(app):
    app.add_project("writing")
    started = utc(2026, 10, 20, 9, 0)
    entry = app.start_pomodoro("writing", note="chapter", tags=["draft"], at=started)
    state = app.pomodoro()
    assert state is not None
    assert state.phase == "focus"
    assert state.planned_seconds == FOCUS_SECONDS
    assert state.entry_id == entry.id
    assert state.remaining_seconds(started) == FOCUS_SECONDS
    assert state.remaining_seconds(started + timedelta(minutes=25)) == 0
    assert state.remaining_seconds(started + timedelta(minutes=26)) == -60
    running = app.running()
    assert running is not None
    assert running.note == "chapter"
    assert running.tags == ("draft",)


def test_second_pomodoro_is_rejected(app):
    app.add_project("writing")
    app.start_pomodoro("writing", at=utc(2026, 10, 20, 9, 0))
    with pytest.raises(TimerAlreadyRunning):
        app.start_pomodoro("writing", at=utc(2026, 10, 20, 9, 10))


def test_stop_clears_the_focus(app):
    app.add_project("writing")
    started = utc(2026, 10, 20, 9, 0)
    app.start_pomodoro("writing", at=started)
    stopped = app.stop(at=started + timedelta(minutes=10))
    assert stopped is not None
    assert stopped.duration_seconds == 600
    assert app.pomodoro() is None
    assert app.running() is None


def test_pomodoro_start_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["pomodoro", "start", "writing", "--note", "chapter"]) == 0
    out = capsys.readouterr().out
    assert "25 minute focus" in out
    assert "5 minutes" in out
    assert main(["pomodoro", "status"]) == 0
    status = capsys.readouterr().out
    assert "Focus:" in status
    assert "0h 25m" in status
