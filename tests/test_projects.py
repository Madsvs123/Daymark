import sqlite3
from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import ProjectArchived, ProjectExists, ProjectNotFound
from daymark.store import Daymark


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


def test_archive_hides_project_from_start_and_keeps_history(app):
    app.add_project("writing")
    app.add_project("reading")
    entry = app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0), note="chapter")
    archived = app.archive_project("writing")
    assert archived.archived is True
    assert [project.name for project in app.list_projects()] == ["reading"]
    assert [project.name for project in app.list_projects(include_archived=True)] == [
        "reading",
        "writing",
    ]
    with pytest.raises(ProjectArchived):
        app.start("writing", at=utc(2026, 10, 20, 12, 0))
    saved = app.get_entry(entry.id)
    assert saved.project == "writing"
    report = app.report_project("writing")
    assert report.total_seconds == 3600
    assert report.entries[0].note == "chapter"


def test_unarchive_makes_start_work_again(app):
    app.add_project("writing")
    app.archive_project("writing")
    restored = app.unarchive_project("writing")
    assert restored.archived is False
    entry = app.start("writing", at=utc(2026, 10, 20, 12, 0))
    assert entry.project == "writing"
    assert entry.ended_at is None


def test_unarchive_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["project", "archive", "writing"]) == 0
    capsys.readouterr()
    assert main(["project", "list", "--all"]) == 0
    assert "writing [archived]" in capsys.readouterr().out
    assert main(["project", "unarchive", "writing"]) == 0
    capsys.readouterr()
    assert main(["project", "list"]) == 0
    assert capsys.readouterr().out.strip() == "writing"


def test_archive_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    assert main(["project", "archive", "writing"]) == 0
    capsys.readouterr()
    assert main(["project", "list"]) == 0
    assert "writing" not in capsys.readouterr().out.lower()
    assert main(["start", "writing"]) == 1
    assert "archived" in capsys.readouterr().err


def test_migrate_adds_archived_column(tmp_path):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO projects (name, created_at) VALUES ('writing', '2026-10-20T09:00:00+00:00')"
    )
    conn.commit()
    conn.close()
    with Daymark(path) as store:
        projects = store.list_projects()
        assert projects[0].name == "writing"
        assert projects[0].archived is False


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
