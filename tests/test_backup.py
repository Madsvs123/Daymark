from datetime import datetime, timezone

import pytest

from daymark.cli import main
from daymark.errors import DaymarkError
from daymark.store import Daymark


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_backup_copies_entries(app, tmp_path):
    app.add_project("writing")
    app.log(
        "writing",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        note="chapter",
        tags=["draft"],
    )
    dest = tmp_path / "copy.db"
    saved = app.backup_to(dest)
    assert saved == dest.resolve()
    with Daymark(dest) as copy:
        entries = copy.entries()
        assert len(entries) == 1
        assert entries[0].project == "writing"
        assert entries[0].note == "chapter"
        assert entries[0].tags == ("draft",)
        assert entries[0].duration_seconds == 3600


def test_backup_refuses_to_overwrite(app, tmp_path):
    dest = tmp_path / "copy.db"
    dest.write_text("keep", encoding="utf-8")
    with pytest.raises(DaymarkError, match="already exists"):
        app.backup_to(dest)
    assert dest.read_text(encoding="utf-8") == "keep"


def test_backup_cli(tmp_path, monkeypatch, capsys):
    db = tmp_path / "daymark.db"
    monkeypatch.setenv("DAYMARK_DB", str(db))
    assert main(["init"]) == 0
    assert main(["project", "add", "writing"]) == 0
    dest = tmp_path / "backups" / "daymark-copy.db"
    dest.parent.mkdir()
    assert main(["backup", "--output", str(dest)]) == 0
    assert "Backed up" in capsys.readouterr().out
    with Daymark(dest) as copy:
        assert [project.name for project in copy.list_projects()] == ["writing"]
