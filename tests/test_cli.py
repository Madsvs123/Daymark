import csv
import io

from daymark.cli import main


def test_cli_daily_flow(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYMARK_DB", str(tmp_path / "daymark.db"))

    assert main(["init"]) == 0
    assert main(["project", "add", "Writing"]) == 0
    assert main(["project", "list"]) == 0
    assert (
        main(
            [
                "log",
                "Writing",
                "--start",
                "2026-10-19 09:00",
                "--end",
                "2026-10-19 11:00",
                "--note",
                "chapter",
                "--tag",
                "draft",
            ]
        )
        == 0
    )
    assert main(["tag", "add", "1", "revise"]) == 0
    assert main(["edit", "1", "--note", "chapter, revised"]) == 0

    capsys.readouterr()
    assert main(["report", "day", "--date", "2026-10-19"]) == 0
    assert "2h 00m" in capsys.readouterr().out

    assert main(["report", "week", "--date", "2026-10-20"]) == 0
    week_out = capsys.readouterr().out
    assert "Week total: 2h 00m" in week_out
    assert "Writing" in week_out
    assert "draft" in week_out

    assert main(["report", "project", "Writing"]) == 0
    assert "2h 00m" in capsys.readouterr().out

    csv_path = tmp_path / "out.csv"
    md_path = tmp_path / "out.md"
    assert main(["export", "csv", "--output", str(csv_path)]) == 0
    assert main(["export", "markdown", "--output", str(md_path)]) == 0
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8"))))
    assert len(rows) == 1
    assert rows[0]["project"] == "Writing"
    assert rows[0]["note"] == "chapter, revised"
    assert rows[0]["duration_seconds"] == "7200"
    assert rows[0]["tags"] == "draft;revise"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Writing" in markdown
    assert "2h 00m" in markdown

    assert main(["start", "Writing", "--note", "live", "--tag", "draft"]) == 0
    capsys.readouterr()
    assert main(["status"]) == 0
    status_out = capsys.readouterr().out
    assert "Running: Writing" in status_out
    assert "live" in status_out

    assert main(["start", "Writing"]) == 1
    assert "already running" in capsys.readouterr().err

    assert main(["stop"]) == 0
    capsys.readouterr()
    assert main(["status"]) == 0
    assert "No timer is running." in capsys.readouterr().out
