from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import ProjectExists, ProjectNotFound


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_rename_keeps_entries(app):
    app.add_project("writing")
    entry = app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0), note="chapter")
    renamed = app.rename_project("Writing", "drafts")
    assert renamed.name == "drafts"
    saved = app.get_entry(entry.id)
    assert saved.project == "drafts"
    assert saved.note == "chapter"
    assert [project.name for project in app.list_projects()] == ["drafts"]


def test_rename_rejects_a_taken_name(app):
    app.add_project("writing")
    app.add_project("reading")
    with pytest.raises(ProjectExists):
        app.rename_project("writing", "reading")


def test_rename_unknown_project(app):
    with pytest.raises(ProjectNotFound):
        app.rename_project("missing", "other")


def test_rename_cli(tmp_path, monkeypatch, capsys):
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
            ]
        )
        == 0
    )
    assert main(["project", "rename", "writing", "drafts"]) == 0
    capsys.readouterr()
    assert main(["project", "list"]) == 0
    assert capsys.readouterr().out.strip() == "drafts"
    assert main(["report", "project", "drafts"]) == 0
    assert "30m" in capsys.readouterr().out or "0h 30m" in capsys.readouterr().out
