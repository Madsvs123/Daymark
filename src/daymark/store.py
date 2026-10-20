"""SQLite storage for one operator's projects, tags, and timer."""

import sqlite3
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path

from daymark.errors import (
    DaymarkError,
    EntryNotFound,
    InvalidInterval,
    NoRunningTimer,
    OverlappingEntry,
    ProjectArchived,
    ProjectExists,
    ProjectNotFound,
    TimerAlreadyRunning,
)
from daymark.models import DayReport, Entry, Pomodoro, Project, ProjectReport, WeekReport
from daymark.timeutil import (
    day_window,
    ensure_utc,
    intervals_overlap,
    iso,
    local_timezone,
    normalize_note,
    normalize_project_name,
    normalize_tags,
    parse_stored,
    utcnow,
    week_window,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    note TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (ended_at IS NULL OR ended_at > started_at)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE
);

CREATE TABLE IF NOT EXISTS entry_tags (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, tag_id)
);

-- One row, id 1, while a timer is open. Prevents a second timer.
CREATE TABLE IF NOT EXISTS open_timer (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    entry_id INTEGER NOT NULL UNIQUE REFERENCES entries(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS entries_started_at ON entries(started_at);
CREATE INDEX IF NOT EXISTS entries_project ON entries(project_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row, id 1, for the operator's current 25/5 pomodoro.
CREATE TABLE IF NOT EXISTS pomodoro (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    phase TEXT NOT NULL CHECK (phase IN ('focus', 'break')),
    started_at TEXT NOT NULL,
    planned_seconds INTEGER NOT NULL,
    entry_id INTEGER REFERENCES entries(id) ON DELETE SET NULL
);
"""

FOCUS_SECONDS = 25 * 60
BREAK_SECONDS = 5 * 60


def default_db_path() -> Path:
    return Path.home() / ".daymark" / "daymark.db"


class Daymark:
    """Local database. Constructing it creates the file and schema if needed."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path).expanduser()
        if self.db_path.exists() and self.db_path.is_dir():
            raise DaymarkError(f"{self.db_path} is a directory, not a database file.")
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DaymarkError(f"Could not create {self.db_path.parent}: {exc}") from exc
        self.db_path = self.db_path.resolve()
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(projects)")}
        if "archived" not in columns:
            self._conn.execute(
                "ALTER TABLE projects ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Daymark":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def set_daily_goal(self, minutes: int) -> int:
        if minutes < 1:
            raise DaymarkError("A daily goal must be at least 1 minute.")
        if minutes > 24 * 60:
            raise DaymarkError("A daily goal must be at most 1440 minutes.")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ('daily_goal_minutes', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(minutes),),
            )
        return minutes

    def daily_goal_minutes(self) -> int | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = 'daily_goal_minutes'"
        ).fetchone()
        if row is None:
            return None
        return int(row["value"])

    def clear_daily_goal(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM settings WHERE key = 'daily_goal_minutes'")

    def add_project(self, name: str) -> Project:
        cleaned = normalize_project_name(name)
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO projects (name, created_at) VALUES (?, ?)",
                    (cleaned, iso(utcnow())),
                )
        except sqlite3.IntegrityError as exc:
            raise ProjectExists(f"Project '{cleaned}' already exists.") from exc
        return self._project(int(cursor.lastrowid))

    def rename_project(self, old: str, new: str) -> Project:
        row = self._require_project(old)
        cleaned = normalize_project_name(new)
        if cleaned.lower() == row["name"].lower():
            if cleaned != row["name"]:
                with self._conn:
                    self._conn.execute(
                        "UPDATE projects SET name = ? WHERE id = ?",
                        (cleaned, row["id"]),
                    )
            return self._project(int(row["id"]))
        try:
            with self._conn:
                self._conn.execute(
                    "UPDATE projects SET name = ? WHERE id = ?",
                    (cleaned, row["id"]),
                )
        except sqlite3.IntegrityError as exc:
            raise ProjectExists(f"Project '{cleaned}' already exists.") from exc
        return self._project(int(row["id"]))

    def archive_project(self, name: str) -> Project:
        row = self._require_project(name)
        if row["archived"]:
            raise DaymarkError(f"Project '{row['name']}' is already archived.")
        running = self.running()
        if running is not None and running.project.lower() == row["name"].lower():
            raise DaymarkError(f"Stop the running timer before archiving '{row['name']}'.")
        with self._conn:
            self._conn.execute("UPDATE projects SET archived = 1 WHERE id = ?", (row["id"],))
        return self._project(int(row["id"]))

    def list_projects(self, *, include_archived: bool = False) -> list[Project]:
        where = "" if include_archived else "WHERE archived = 0"
        rows = self._conn.execute(
            f"""
            SELECT id, name, created_at, archived
            FROM projects
            {where}
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [
            Project(
                id=row["id"],
                name=row["name"],
                created_at=parse_stored(row["created_at"]),
                archived=bool(row["archived"]),
            )
            for row in rows
        ]

    def start(
        self,
        project: str,
        *,
        note: str = "",
        tags: list[str] | None = None,
        at: datetime | None = None,
    ) -> Entry:
        row = self._require_project(project)
        if row["archived"]:
            raise ProjectArchived(
                f"Project '{row['name']}' is archived, so it is not available to start. "
                "Its earlier entries stay in your history."
            )
        running = self.running()
        if running is not None:
            raise TimerAlreadyRunning(
                f"A timer is already running for '{running.project}' (entry {running.id}). "
                "Stop it before starting another."
            )
        started = ensure_utc(at or utcnow())
        self._reject_overlap(started, None)
        clean_note = normalize_note(note)
        clean_tags = normalize_tags(tags)
        stamp = iso(utcnow())
        try:
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO entries
                        (project_id, note, started_at, ended_at, created_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?)
                    """,
                    (row["id"], clean_note, iso(started), stamp, stamp),
                )
                entry_id = int(cursor.lastrowid)
                self._attach_tags(entry_id, clean_tags)
                self._conn.execute(
                    "INSERT INTO open_timer (id, entry_id) VALUES (1, ?)",
                    (entry_id,),
                )
                self._conn.execute("DELETE FROM pomodoro WHERE phase = 'break'")
        except sqlite3.IntegrityError as exc:
            raise TimerAlreadyRunning(
                "A timer is already running. Stop it before starting another."
            ) from exc
        return self.get_entry(entry_id)

    def stop(
        self,
        *,
        note: str | None = None,
        at: datetime | None = None,
        discard: bool = False,
    ) -> Entry | None:
        running = self.running()
        if running is None:
            raise NoRunningTimer("No timer is running.")
        if discard:
            with self._conn:
                self._conn.execute("DELETE FROM entries WHERE id = ?", (running.id,))
                self._conn.execute("DELETE FROM pomodoro WHERE entry_id = ?", (running.id,))
            return None
        end = ensure_utc(at) if at is not None else utcnow()
        if at is None and end <= running.started_at:
            end = running.started_at + timedelta(seconds=1)
        if end <= running.started_at:
            raise InvalidInterval("Stop time must be after the start time.")
        self._reject_overlap(running.started_at, end, exclude_id=running.id)
        new_note = running.note if note is None else normalize_note(note)
        with self._conn:
            self._conn.execute(
                """
                UPDATE entries
                SET note = ?, ended_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_note, iso(end), iso(utcnow()), running.id),
            )
            self._conn.execute("DELETE FROM open_timer WHERE entry_id = ?", (running.id,))
            self._conn.execute("DELETE FROM pomodoro WHERE entry_id = ?", (running.id,))
        return self.get_entry(running.id)

    def start_pomodoro(
        self,
        project: str,
        *,
        note: str = "",
        tags: list[str] | None = None,
        at: datetime | None = None,
    ) -> Entry:
        """Start the single timer as a 25 minute focus. The break is 5 minutes."""
        entry = self.start(project, note=note, tags=tags, at=at)
        with self._conn:
            self._conn.execute("DELETE FROM pomodoro")
            self._conn.execute(
                """
                INSERT INTO pomodoro (id, phase, started_at, planned_seconds, entry_id)
                VALUES (1, 'focus', ?, ?, ?)
                """,
                (iso(entry.started_at), FOCUS_SECONDS, entry.id),
            )
        return entry

    def begin_break(self, *, at: datetime | None = None) -> Pomodoro:
        """Stop the focus entry and record a fixed 5 minute break."""
        state = self.pomodoro()
        if state is None or state.phase != "focus":
            raise DaymarkError(
                "No focus session is running. Start one with `daymark pomodoro start`."
            )
        now = ensure_utc(at) if at is not None else utcnow()
        if now <= state.started_at:
            now = state.started_at + timedelta(seconds=1)
        self.stop(at=now)
        with self._conn:
            self._conn.execute("DELETE FROM pomodoro")
            self._conn.execute(
                """
                INSERT INTO pomodoro (id, phase, started_at, planned_seconds, entry_id)
                VALUES (1, 'break', ?, ?, NULL)
                """,
                (iso(now), BREAK_SECONDS),
            )
        started = self.pomodoro()
        if started is None:
            raise DaymarkError("The break could not be saved.")
        return started

    def finish_pomodoro(self) -> None:
        state = self.pomodoro()
        if state is None:
            raise DaymarkError("No pomodoro is running.")
        if state.phase == "focus":
            raise DaymarkError("A focus is still running. Use `daymark pomodoro break` or `daymark stop`.")
        with self._conn:
            self._conn.execute("DELETE FROM pomodoro")

    def pomodoro(self) -> Pomodoro | None:
        row = self._conn.execute(
            "SELECT phase, started_at, planned_seconds, entry_id FROM pomodoro WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        return Pomodoro(
            phase=row["phase"],
            started_at=parse_stored(row["started_at"]),
            planned_seconds=int(row["planned_seconds"]),
            entry_id=row["entry_id"],
        )

    def running(self) -> Entry | None:
        rows = self._fetch_entries("WHERE e.ended_at IS NULL", ())
        if not rows:
            return None
        if len(rows) > 1:
            raise DaymarkError("More than one timer is open. That should not happen.")
        return rows[0]

    def log(
        self,
        project: str,
        started_at: datetime,
        ended_at: datetime,
        *,
        note: str = "",
        tags: list[str] | None = None,
    ) -> Entry:
        row = self._require_project(project)
        start = ensure_utc(started_at)
        end = ensure_utc(ended_at)
        self._validate_interval(start, end)
        overlap = self._find_overlap(start, end)
        if overlap is not None and overlap.ended_at is None:
            raise TimerAlreadyRunning(
                f"That range overlaps the running timer for '{overlap.project}' "
                f"(entry {overlap.id})."
            )
        if overlap is not None:
            raise OverlappingEntry(self._overlap_message(overlap))
        clean_note = normalize_note(note)
        clean_tags = normalize_tags(tags)
        stamp = iso(utcnow())
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO entries
                    (project_id, note, started_at, ended_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row["id"], clean_note, iso(start), iso(end), stamp, stamp),
            )
            entry_id = int(cursor.lastrowid)
            self._attach_tags(entry_id, clean_tags)
        return self.get_entry(entry_id)

    def edit(
        self,
        entry_id: int,
        *,
        project: str | None = None,
        note: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> Entry:
        if project is None and note is None and started_at is None and ended_at is None:
            raise DaymarkError("Provide a field to change, such as --note or --start.")
        current = self.get_entry(entry_id)
        new_project = current.project if project is None else normalize_project_name(project)
        new_note = current.note if note is None else normalize_note(note)
        new_start = current.started_at if started_at is None else ensure_utc(started_at)
        new_end = current.ended_at if ended_at is None else ensure_utc(ended_at)
        self._validate_interval(new_start, new_end)
        overlap = self._find_overlap(new_start, new_end, exclude_id=entry_id)
        if overlap is not None and overlap.ended_at is None and new_end is None:
            raise TimerAlreadyRunning(
                f"That range overlaps the running timer for '{overlap.project}' "
                f"(entry {overlap.id})."
            )
        if overlap is not None:
            raise OverlappingEntry(self._overlap_message(overlap))
        project_row = self._require_project(new_project)
        closing = current.ended_at is None and new_end is not None
        with self._conn:
            self._conn.execute(
                """
                UPDATE entries
                SET project_id = ?, note = ?, started_at = ?, ended_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    project_row["id"],
                    new_note,
                    iso(new_start),
                    iso(new_end) if new_end is not None else None,
                    iso(utcnow()),
                    entry_id,
                ),
            )
            if closing:
                self._conn.execute("DELETE FROM open_timer WHERE entry_id = ?", (entry_id,))
                self._conn.execute("DELETE FROM pomodoro WHERE entry_id = ?", (entry_id,))
        return self.get_entry(entry_id)

    def add_tags(self, entry_id: int, tags: list[str]) -> Entry:
        self.get_entry(entry_id)
        clean = normalize_tags(tags)
        if not clean:
            raise DaymarkError("Provide at least one tag.")
        with self._conn:
            self._attach_tags(entry_id, clean)
            self._touch(entry_id)
        return self.get_entry(entry_id)

    def remove_tags(self, entry_id: int, tags: list[str]) -> Entry:
        self.get_entry(entry_id)
        clean = normalize_tags(tags)
        if not clean:
            raise DaymarkError("Provide at least one tag.")
        with self._conn:
            for tag in clean:
                row = self._conn.execute(
                    """
                    SELECT t.id
                    FROM tags t
                    JOIN entry_tags et ON et.tag_id = t.id
                    WHERE et.entry_id = ? AND t.name = ? COLLATE NOCASE
                    """,
                    (entry_id, tag),
                ).fetchone()
                if row is None:
                    raise DaymarkError(f"Entry {entry_id} does not have tag '{tag}'.")
                self._conn.execute(
                    "DELETE FROM entry_tags WHERE entry_id = ? AND tag_id = ?",
                    (entry_id, row["id"]),
                )
            self._touch(entry_id)
        return self.get_entry(entry_id)

    def get_entry(self, entry_id: int) -> Entry:
        rows = self._fetch_entries("WHERE e.id = ?", (entry_id,))
        if not rows:
            raise EntryNotFound(f"No entry {entry_id}.")
        return rows[0]

    def entries(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        project: str | None = None,
        completed_only: bool = False,
    ) -> list[Entry]:
        clauses: list[str] = []
        params: list[object] = []
        if completed_only:
            clauses.append("e.ended_at IS NOT NULL")
        if start is not None:
            clauses.append("e.started_at >= ?")
            params.append(iso(ensure_utc(start)))
        if end is not None:
            clauses.append("e.started_at < ?")
            params.append(iso(ensure_utc(end)))
        if project is not None:
            clauses.append("p.name = ? COLLATE NOCASE")
            params.append(normalize_project_name(project))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._fetch_entries(where, tuple(params))

    def report_day(self, day: date | None = None, tz: tzinfo | None = None) -> DayReport:
        zone = tz or local_timezone()
        target = day or datetime.now(zone).date()
        start, end = day_window(target, zone)
        entries = tuple(self.entries(start=start, end=end, completed_only=True))
        running = self._running_in_window(start, end)
        total = sum(entry.duration_seconds or 0 for entry in entries)
        return DayReport(
            day=target,
            total_seconds=total,
            entries=entries,
            running=running,
            goal_minutes=self.daily_goal_minutes(),
        )

    def report_week(self, day: date | None = None, tz: tzinfo | None = None) -> WeekReport:
        """Group completed entries that started during the Monday-Sunday week of `day`."""
        zone = tz or local_timezone()
        anchor = day or datetime.now(zone).date()
        start, end, start_date, end_date = week_window(anchor, zone)
        entries = tuple(self.entries(start=start, end=end, completed_only=True))
        by_project: dict[str, int] = {}
        by_tag: dict[str, int] = {}
        by_project_tag: dict[str, dict[str, int]] = {}
        total = 0
        for entry in entries:
            seconds = entry.duration_seconds or 0
            total += seconds
            by_project[entry.project] = by_project.get(entry.project, 0) + seconds
            tag_names = entry.tags or ("",)
            bucket = by_project_tag.setdefault(entry.project, {})
            for tag in tag_names:
                by_tag[tag] = by_tag.get(tag, 0) + seconds
                bucket[tag] = bucket.get(tag, 0) + seconds
        return WeekReport(
            start_date=start_date,
            end_date=end_date,
            total_seconds=total,
            by_project=by_project,
            by_tag=by_tag,
            by_project_tag=by_project_tag,
            entries=entries,
        )

    def report_project(
        self,
        name: str,
        *,
        start: date | None = None,
        end: date | None = None,
        tz: tzinfo | None = None,
    ) -> ProjectReport:
        zone = tz or local_timezone()
        row = self._require_project(name)
        if start is not None and end is not None and start > end:
            raise DaymarkError("The start date must be on or before the end date.")
        start_dt = day_window(start, zone)[0] if start is not None else None
        end_dt = day_window(end, zone)[1] if end is not None else None
        entries = tuple(
            self.entries(
                start=start_dt,
                end=end_dt,
                project=row["name"],
                completed_only=True,
            )
        )
        running = self.running()
        if running is None or running.project.lower() != row["name"].lower():
            running = None
        elif start_dt is not None and running.started_at < start_dt:
            running = None
        elif end_dt is not None and running.started_at >= end_dt:
            running = None
        total = sum(entry.duration_seconds or 0 for entry in entries)
        return ProjectReport(
            project=row["name"],
            total_seconds=total,
            entries=entries,
            running=running,
        )

    def _running_in_window(self, start: datetime, end: datetime) -> Entry | None:
        running = self.running()
        if running is None:
            return None
        if start <= running.started_at < end:
            return running
        return None

    def _project(self, project_id: int) -> Project:
        row = self._conn.execute(
            "SELECT id, name, created_at, archived FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if row is None:
            raise ProjectNotFound(f"No project with id {project_id}.")
        return Project(
            id=row["id"],
            name=row["name"],
            created_at=parse_stored(row["created_at"]),
            archived=bool(row["archived"]),
        )

    def _require_project(self, name: str) -> sqlite3.Row:
        cleaned = normalize_project_name(name)
        row = self._conn.execute(
            "SELECT id, name, created_at, archived FROM projects WHERE name = ? COLLATE NOCASE",
            (cleaned,),
        ).fetchone()
        if row is None:
            raise ProjectNotFound(
                f"No project named '{cleaned}'. Add it with: daymark project add \"{cleaned}\""
            )
        return row

    def _attach_tags(self, entry_id: int, tags: tuple[str, ...]) -> None:
        for tag in tags:
            self._conn.execute(
                "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (tag,),
            )
            tag_row = self._conn.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE",
                (tag,),
            ).fetchone()
            self._conn.execute(
                "INSERT OR IGNORE INTO entry_tags (entry_id, tag_id) VALUES (?, ?)",
                (entry_id, tag_row["id"]),
            )

    def _touch(self, entry_id: int) -> None:
        self._conn.execute(
            "UPDATE entries SET updated_at = ? WHERE id = ?",
            (iso(utcnow()), entry_id),
        )

    def _validate_interval(self, start: datetime, end: datetime | None) -> None:
        if end is not None and end <= start:
            raise InvalidInterval("The end time must be after the start time.")

    def _reject_overlap(
        self,
        start: datetime,
        end: datetime | None,
        *,
        exclude_id: int | None = None,
    ) -> None:
        overlap = self._find_overlap(start, end, exclude_id=exclude_id)
        if overlap is not None:
            raise OverlappingEntry(self._overlap_message(overlap))

    def _find_overlap(
        self,
        start: datetime,
        end: datetime | None,
        *,
        exclude_id: int | None = None,
    ) -> Entry | None:
        for entry in self._fetch_entries("", ()):
            if exclude_id is not None and entry.id == exclude_id:
                continue
            if intervals_overlap(start, end, entry.started_at, entry.ended_at):
                return entry
        return None

    def _overlap_message(self, entry: Entry) -> str:
        return f"That range overlaps entry {entry.id} ({entry.project})."

    def _fetch_entries(self, where: str, params: tuple[object, ...]) -> list[Entry]:
        rows = self._conn.execute(
            f"""
            SELECT e.id, p.name AS project, e.note, e.started_at, e.ended_at
            FROM entries e
            JOIN projects p ON p.id = e.project_id
            {where}
            ORDER BY e.started_at, e.id
            """,
            params,
        ).fetchall()
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(ids))
        tag_rows = self._conn.execute(
            f"""
            SELECT et.entry_id, t.name
            FROM entry_tags et
            JOIN tags t ON t.id = et.tag_id
            WHERE et.entry_id IN ({placeholders})
            ORDER BY t.name COLLATE NOCASE
            """,
            ids,
        ).fetchall()
        tags: dict[int, list[str]] = {}
        for tag_row in tag_rows:
            tags.setdefault(tag_row["entry_id"], []).append(tag_row["name"])
        return [
            Entry(
                id=row["id"],
                project=row["project"],
                note=row["note"],
                tags=tuple(tags.get(row["id"], ())),
                started_at=parse_stored(row["started_at"]),
                ended_at=parse_stored(row["ended_at"]) if row["ended_at"] else None,
            )
            for row in rows
        ]
