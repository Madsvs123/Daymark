from datetime import datetime, time, timedelta, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError
from daymark.render import goal_met_line, render_day
from daymark.timeutil import parse_goal_minutes


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_parse_goal_minutes():
    assert parse_goal_minutes("90") == 90
    assert parse_goal_minutes("1h30m") == 90
    assert parse_goal_minutes("2h") == 120
    with pytest.raises(DaymarkError):
        parse_goal_minutes("90s")
    with pytest.raises(DaymarkError):
        parse_goal_minutes("0")


def test_daily_goal_round_trip(app):
    assert app.daily_goal_minutes() is None
    assert app.set_daily_goal(90) == 90
    assert app.daily_goal_minutes() == 90
    app.set_daily_goal(60)
    assert app.daily_goal_minutes() == 60
    app.clear_daily_goal()
    assert app.daily_goal_minutes() is None


def test_goal_met_line_appears_only_when_reached():
    assert goal_met_line(59 * 60, 60) is None
    assert goal_met_line(60 * 60, None) is None
    line = goal_met_line(90 * 60, 60)
    assert line == "Daily goal met: 1h 30m of 1h 00m."


def test_day_report_includes_goal_line(app):
    app.add_project("writing")
    app.set_daily_goal(30)
    app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0))
    report = app.report_day(datetime(2026, 10, 20, tzinfo=timezone.utc).date(), tz=timezone.utc)
    text = render_day(report)
    assert "Daily goal met: 1h 00m of 0h 30m." in text


def test_status_prints_goal_line_without_a_timer(tmp_path, monkeypatch, capsys):
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
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "No timer is running." in out
    assert "Daily goal met:" in out


def test_goal_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["goal", "show"]) == 0
    assert "No daily goal" in capsys.readouterr().out
    assert main(["goal", "set", "1h30m"]) == 0
    assert "1h 30m" in capsys.readouterr().out
    assert main(["goal", "show"]) == 0
    assert "Daily goal: 1h 30m." in capsys.readouterr().out
    assert main(["goal", "clear"]) == 0
    assert main(["goal", "show"]) == 0
    assert "No daily goal" in capsys.readouterr().out
