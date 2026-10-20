from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_rename_tag_updates_every_entry(app):
    app.add_project("writing")
    app.add_project("reading")
    first = app.log(
        "writing",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        tags=["draft"],
    )
    second = app.log(
        "reading",
        utc(2026, 10, 20, 11, 0),
        utc(2026, 10, 20, 12, 0),
        tags=["draft", "focus"],
    )
    name, count = app.rename_tag("Draft", "revise")
    assert name == "revise"
    assert count == 2
    assert app.get_entry(first.id).tags == ("revise",)
    assert app.get_entry(second.id).tags == ("focus", "revise")


def test_rename_tag_merges_when_the_new_name_exists(app):
    app.add_project("writing")
    entry = app.log(
        "writing",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        tags=["draft", "revise"],
    )
    app.rename_tag("draft", "revise")
    assert app.get_entry(entry.id).tags == ("revise",)


def test_rename_missing_tag(app):
    with pytest.raises(DaymarkError, match="No tag"):
        app.rename_tag("missing", "other")


def test_rename_tag_cli(tmp_path, monkeypatch, capsys):
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
                "--tag",
                "draft",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["tag", "rename", "draft", "revise"]) == 0
    assert "Renamed tag to 'revise' on 1 entry." in capsys.readouterr().out
    assert main(["report", "week", "--date", "2026-10-20"]) == 0
    week = capsys.readouterr().out
    assert "revise" in week
    assert "draft" not in week
