from datetime import date, datetime, timezone

from daymark.render import render_week, sparkline


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_sparkline_scales_to_the_peak():
    assert sparkline((0, 0, 0)) == "···"
    assert sparkline(()) == ""
    line = sparkline((0, 10, 20, 40))
    assert line[0] == "·"
    assert line[-1] == "█"
    assert len(line) == 4


def test_week_report_sparkline_follows_monday_to_sunday(app):
    app.add_project("writing")
    # Week of 2026-10-19 (Monday) to 2026-10-25 (Sunday), UTC.
    app.log("writing", utc(2026, 10, 19, 9, 0), utc(2026, 10, 19, 10, 0))
    app.log("writing", utc(2026, 10, 21, 9, 0), utc(2026, 10, 21, 13, 0))
    app.log("writing", utc(2026, 10, 25, 9, 0), utc(2026, 10, 25, 10, 0))

    report = app.report_week(date(2026, 10, 20), tz=timezone.utc)

    assert report.daily_seconds == (3600, 0, 14400, 0, 0, 0, 3600)
    text = render_week(report)
    line = sparkline(report.daily_seconds)
    assert line[0] != "·"
    assert line[1] == "·"
    assert line[2] == "█"
    assert line[-1] != "·"
    assert f"Daily sparkline (Mon-Sun): {line}" in text
