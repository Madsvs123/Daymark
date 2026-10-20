import pytest

from daymark.cli import main
from daymark.errors import DaymarkError
from daymark.timeutil import parse_goal_minutes


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
