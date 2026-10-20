from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError, EntryNotFound


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_delete_removes_a_finished_entry(app):
    app.add_project("writing")
    entry = app.log(
        "writing",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        note="chapter",
        tags=["draft"],
    )
    deleted = app.delete_entry(entry.id)
    assert deleted.id == entry.id
    assert app.entries() == []
    with pytest.raises(EntryNotFound):
        app.get_entry(entry.id)


def test_delete_refuses_the_running_timer(app):
    app.add_project("writing")
    entry = app.start("writing", at=utc(2026, 10, 20, 9, 0))
    with pytest.raises(DaymarkError, match="running timer"):
        app.delete_entry(entry.id)
    assert app.running() is not None


def test_delete_cli(tmp_path, monkeypatch, capsys):
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
                "30m",
                "--note",
                "chapter",
            ]
        )
        == 0
    )
    assert main(["delete", "1"]) == 0
    assert "Deleted entry 1" in capsys.readouterr().out
    assert main(["report", "project", "writing"]) == 0
    assert "No completed entries." in capsys.readouterr().out
