"""One local-timer session covering the commands added after the first commit."""

import json
from datetime import date

from daymark.cli import main
from daymark.store import Daymark


def test_operator_session(tmp_path, monkeypatch, capsys):
    db = tmp_path / "daymark.db"
    monkeypatch.setenv("DAYMARK_DB", str(db))

    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["project", "add", "reading"]) == 0
    assert main(["goal", "set", "30"]) == 0

    assert (
        main(
            [
                "log",
                "writing",
                "--start",
                "2026-10-20 09:00",
                "--duration",
                "1h20m",
                "--note",
                "outline",
                "--tag",
                "draft",
            ]
        )
        == 0
    )
    assert main(["note", "1", "revised", "outline"]) == 0
    assert main(["tag", "rename", "draft", "revise"]) == 0
    capsys.readouterr()
    assert main(["split", "1", "40"]) == 0
    split_out = capsys.readouterr().out
    assert "0h 40m" in split_out
    assert "0h 40m" in split_out

    assert main(["delete", "2"]) == 0
    assert main(["project", "rename", "writing", "drafts"]) == 0
    capsys.readouterr()
    assert main(["report", "month", "--date", "2026-10"]) == 0
    month = capsys.readouterr().out
    assert "drafts" in month
    assert "0h 40m" in month

    assert main(["report", "week", "--date", "2026-10-20"]) == 0
    week = capsys.readouterr().out
    assert "Daily sparkline (Mon-Sun):" in week
    assert "revise" in week

    assert main(["project", "archive", "reading"]) == 0
    capsys.readouterr()
    assert main(["project", "list"]) == 0
    listed = capsys.readouterr().out
    assert "drafts" in listed
    assert "reading" not in listed
    assert main(["project", "unarchive", "reading"]) == 0

    capsys.readouterr()
    assert main(["continue", "--note", "more drafting"]) == 0
    assert "Continued drafts" in capsys.readouterr().out
    assert main(["stop", "--discard"]) == 0

    assert main(["pomodoro", "start", "reading"]) == 0
    capsys.readouterr()
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is True
    assert payload["project"] == "reading"
    assert payload["pomodoro"]["phase"] == "focus"
    assert payload["pomodoro"]["planned_seconds"] == 25 * 60
    assert payload["daily_goal_minutes"] == 30

    assert main(["pomodoro", "break"]) == 0
    assert main(["pomodoro", "done"]) == 0
    capsys.readouterr()
    assert main(["doctor"]) == 0
    assert "daymark doctor: ok" in capsys.readouterr().out

    backup = tmp_path / "daymark-backup.db"
    assert main(["backup", "--output", str(backup)]) == 0
    assert main(["delete", "1"]) == 0
    assert main(["restore", "--from", str(backup)]) == 0

    with Daymark(db) as store:
        notes = [entry.note for entry in store.entries()]
        assert "revised outline" in notes
        report = store.report_month(date(2026, 10, 20))
        assert report.by_project["drafts"] >= 40 * 60
