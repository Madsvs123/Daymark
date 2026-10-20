from datetime import datetime, timedelta, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError
from daymark.timeutil import parse_duration


def test_parse_duration_forms():
    assert parse_duration("1h20m") == 80 * 60
    assert parse_duration("90m") == 90 * 60
    assert parse_duration("2h") == 2 * 3600
    assert parse_duration("45s") == 45
    assert parse_duration("1h 20m 30s") == 3600 + 20 * 60 + 30
    assert parse_duration("0h15m") == 15 * 60


def test_parse_duration_rejects_empty_zero_and_junk():
    with pytest.raises(DaymarkError):
        parse_duration("   ")
    with pytest.raises(DaymarkError):
        parse_duration("0m")
    with pytest.raises(DaymarkError):
        parse_duration("about an hour")
    with pytest.raises(DaymarkError):
        parse_duration("20")


def test_log_duration_from_cli(tmp_path, monkeypatch, capsys):
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
                "1h20m",
                "--note",
                "draft",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "1h 20m" in out

    started = datetime(2026, 10, 20, 9, 0).astimezone()
    ended = started + timedelta(minutes=80)
    assert ended.strftime("%Y-%m-%d %H:%M") in out
