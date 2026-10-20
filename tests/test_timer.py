from datetime import datetime, timedelta, timezone

import pytest

from daymark.errors import (
    InvalidInterval,
    OverlappingEntry,
    ProjectExists,
    TimerAlreadyRunning,
)
from daymark.store import Daymark


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def test_start_stop_duration(tmp_path):
    path = tmp_path / "daymark.db"
    started = utc(2026, 10, 20, 9, 0)
    with Daymark(path) as store:
        store.add_project("writing")
        store.start("writing", note="draft", tags=["deep"], at=started)

    with Daymark(path) as store:
        running = store.running()
        assert running is not None
        assert running.project == "writing"
        assert running.note == "draft"
        assert running.tags == ("deep",)
        assert running.ended_at is None
        stopped = store.stop(at=started + timedelta(minutes=90))

    assert stopped is not None
    assert stopped.duration_seconds == 5400
    with Daymark(path) as store:
        assert store.running() is None
        saved = store.get_entry(stopped.id)
        assert saved.duration_seconds == 5400
        assert saved.tags == ("deep",)


def test_overlapping_timer_rejected(tmp_path):
    path = tmp_path / "daymark.db"
    with Daymark(path) as store:
        store.add_project("alpha")
        store.add_project("beta")
        store.start("alpha", at=utc(2026, 10, 20, 9, 0))

    with Daymark(path) as store:
        with pytest.raises(TimerAlreadyRunning, match="already running"):
            store.start("beta")
        running = store.running()
        assert running is not None
        assert running.project == "alpha"


def test_manual_entry_overlap_rejected(app):
    app.add_project("Alpha")
    app.log("Alpha", utc(2026, 10, 20, 9, 0), utc(2026, 10, 20, 11, 0))
    with pytest.raises(OverlappingEntry):
        app.log("Alpha", utc(2026, 10, 20, 10, 0), utc(2026, 10, 20, 12, 0))


def test_end_must_follow_start(app):
    app.add_project("Alpha")
    with pytest.raises(InvalidInterval):
        app.log("Alpha", utc(2026, 10, 20, 11, 0), utc(2026, 10, 20, 10, 0))


def test_duplicate_project_rejected(app):
    app.add_project("Writing")
    with pytest.raises(ProjectExists):
        app.add_project("writing")


def test_edit_note_and_move(app):
    app.add_project("Alpha")
    app.add_project("Beta")
    entry = app.log(
        "Alpha",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        note="old",
    )
    renamed = app.edit(entry.id, note="new")
    assert renamed.note == "new"
    assert renamed.duration_seconds == 3600
    moved = app.edit(
        entry.id,
        project="Beta",
        started_at=utc(2026, 10, 20, 9, 15),
        ended_at=utc(2026, 10, 20, 10, 15),
    )
    assert moved.project == "Beta"
    assert moved.duration_seconds == 3600


def test_tag_add_and_remove(app):
    app.add_project("Alpha")
    entry = app.log(
        "Alpha",
        utc(2026, 10, 20, 9, 0),
        utc(2026, 10, 20, 10, 0),
        tags=["focus"],
    )
    tagged = app.add_tags(entry.id, ["Admin"])
    assert tagged.tags == ("admin", "focus")
    removed = app.remove_tags(entry.id, ["focus"])
    assert removed.tags == ("admin",)


def test_discard_releases_the_timer(app):
    app.add_project("Alpha")
    app.start("Alpha", at=utc(2026, 10, 20, 9, 0))
    assert app.stop(discard=True) is None
    assert app.running() is None
    assert app.entries() == []
    again = app.start("Alpha", at=utc(2026, 10, 20, 12, 0))
    assert again.ended_at is None
