from datetime import datetime, timezone

from daymark.cli import main


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_doctor_accepts_a_healthy_database(app):
    app.add_project("writing")
    app.log("writing", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 10, 0), tags=["draft"])
    assert app.doctor() == []


def test_doctor_flags_a_timer_row_that_does_not_match(app):
    app.add_project("writing")
    app.start("writing", at=utc(2026, 10, 20, 9, 0))
    app._conn.execute("DELETE FROM open_timer")
    app._conn.commit()
    problems = app.doctor()
    assert "the open timer does not match the open entry" in problems


def test_doctor_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "daymark doctor: ok" in out
    assert "Database:" in out
