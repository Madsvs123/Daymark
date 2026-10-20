from datetime import date, datetime, timezone

from daymark.cli import main
from daymark.render import render_month


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_month_report_keeps_calendar_bounds(app):
    app.add_project("writing")
    app.add_project("reading")
    app.log("writing", utc(2026, 9, 30, 22, 0), utc(2026, 9, 30, 23, 0), note="before")
    app.log("writing", utc(2026, 10, 1, 0, 0), utc(2026, 10, 1, 2, 0), note="open")
    app.log("reading", utc(2026, 10, 31, 22, 0), utc(2026, 10, 31, 23, 0), note="close")
    app.log("reading", utc(2026, 11, 1, 0, 0), utc(2026, 11, 1, 1, 0), note="after")

    report = app.report_month(date(2026, 10, 20), tz=timezone.utc)

    assert report.start_date == date(2026, 10, 1)
    assert report.end_date == date(2026, 10, 31)
    assert report.total_seconds == 3 * 3600
    assert report.by_project == {"writing": 2 * 3600, "reading": 3600}
    assert {entry.note for entry in report.entries} == {"open", "close"}
    text = render_month(report)
    assert "Month of 2026-10-01 to 2026-10-31" in text
    assert "Month total: 3h 00m" in text
    assert "writing: 2h 00m" in text
    assert "reading: 1h 00m" in text


def test_month_cli_accepts_year_month(tmp_path, monkeypatch, capsys):
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
                "90m",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["report", "month", "--date", "2026-10"]) == 0
    out = capsys.readouterr().out
    assert "Month of 2026-10-01 to 2026-10-31" in out
    assert "writing" in out
    assert "1h 30m" in out
