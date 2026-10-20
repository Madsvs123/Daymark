import csv
import io
from datetime import date, datetime, timezone

from daymark.render import render_csv, render_markdown, render_week


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_week_report_totals(app):
    app.add_project("Alpha")
    app.add_project("Beta")
    app.log("Alpha", utc(2026, 10, 19, 9, 0), utc(2026, 10, 19, 11, 0), note="plan", tags=["focus"])
    app.log(
        "Alpha",
        utc(2026, 10, 20, 14, 0),
        utc(2026, 10, 20, 15, 30),
        note="mail",
        tags=["admin", "focus"],
    )
    app.log("Beta", utc(2026, 10, 21, 10, 0), utc(2026, 10, 21, 11, 0), note="read")
    app.log("Beta", utc(2026, 10, 12, 10, 0), utc(2026, 10, 12, 12, 0), note="old", tags=["focus"])
    app.log("Beta", utc(2026, 10, 18, 23, 0), utc(2026, 10, 18, 23, 30), note="before", tags=["focus"])
    app.log("Beta", utc(2026, 10, 26, 0, 0), utc(2026, 10, 26, 1, 0), note="after", tags=["focus"])

    report = app.report_week(date(2026, 10, 20), tz=timezone.utc)

    assert report.start_date == date(2026, 10, 19)
    assert report.end_date == date(2026, 10, 25)
    assert report.total_seconds == 16200
    assert report.by_project == {"Alpha": 12600, "Beta": 3600}
    assert sum(report.by_project.values()) == report.total_seconds
    assert report.by_tag["focus"] == 12600
    assert report.by_tag["admin"] == 5400
    assert report.by_tag[""] == 3600
    assert set(report.by_tag) == {"focus", "admin", ""}
    assert report.by_project_tag["Alpha"]["focus"] == 12600
    assert report.by_project_tag["Alpha"]["admin"] == 5400
    assert report.by_project_tag["Beta"][""] == 3600
    assert {entry.note for entry in report.entries} == {"plan", "mail", "read"}

    text = render_week(report)
    assert "Week of 2026-10-19 to 2026-10-25" in text
    assert "Alpha" in text
    assert "Beta" in text
    assert "(untagged)" in text
    assert "Week total: 4h 30m" in text
    assert "3h 30m" in text
    assert "1h 00m" in text


def test_csv_export(app):
    app.add_project("Alpha")
    app.log(
        "Alpha",
        utc(2026, 10, 19, 9, 0),
        utc(2026, 10, 19, 11, 0),
        note="plan, revise",
        tags=["focus", "admin"],
    )
    text = render_csv(app.entries())
    assert text.startswith("id,project,note,tags,started_at,ended_at,duration_seconds\n")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 1
    row = rows[0]
    assert row["project"] == "Alpha"
    assert row["note"] == "plan, revise"
    assert row["tags"] == "admin;focus"
    assert row["started_at"] == "2026-10-19T09:00:00+00:00"
    assert row["ended_at"] == "2026-10-19T11:00:00+00:00"
    assert row["duration_seconds"] == "7200"


def test_markdown_export_includes_total(app):
    app.add_project("Alpha")
    app.log(
        "Alpha",
        utc(2026, 10, 19, 9, 0),
        utc(2026, 10, 19, 11, 0),
        note="plan",
        tags=["focus"],
    )
    text = render_markdown(app.entries())
    assert "# Daymark export" in text
    assert "Alpha" in text
    assert "**Total completed:** 2h 00m" in text

