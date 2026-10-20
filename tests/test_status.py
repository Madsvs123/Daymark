import json
from datetime import datetime, time, timedelta, timezone

from daymark.cli import main


def test_status_json_when_idle(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["entry_id"] is None
    assert payload["project"] is None
    assert payload["elapsed_seconds"] is None
    assert payload["tags"] == []
    assert payload["daily_goal_minutes"] is None
    assert payload["goal_met"] is False
    assert payload["pomodoro"] is None
    assert payload["today_seconds"] == 0


def test_status_json_reports_a_met_goal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["goal", "set", "1"]) == 0
    zone = datetime.now().astimezone().tzinfo
    start = datetime.combine(datetime.now().astimezone().date(), time(0, 0), tzinfo=zone)
    end = start + timedelta(minutes=1)
    assert (
        main(
            [
                "log",
                "writing",
                "--start",
                start.strftime("%Y-%m-%d %H:%M"),
                "--end",
                end.strftime("%Y-%m-%d %H:%M"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is False
    assert payload["daily_goal_minutes"] == 1
    assert payload["today_seconds"] == 60
    assert payload["goal_met"] is True


def test_status_json_includes_the_running_pomodoro(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["pomodoro", "start", "writing", "--note", "chapter", "--tag", "draft"]) == 0
    capsys.readouterr()
    assert main(["status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["running"] is True
    assert payload["project"] == "writing"
    assert payload["note"] == "chapter"
    assert payload["tags"] == ["draft"]
    assert payload["elapsed_seconds"] >= 0
    assert payload["started_at"].endswith("+00:00")
    assert payload["pomodoro"]["phase"] == "focus"
    assert payload["pomodoro"]["planned_seconds"] == 25 * 60
