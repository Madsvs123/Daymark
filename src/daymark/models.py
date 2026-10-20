"""Records returned by the database."""

from dataclasses import dataclass
from datetime import datetime, date


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    created_at: datetime
    archived: bool = False


@dataclass(frozen=True)
class Entry:
    id: int
    project: str
    note: str
    tags: tuple[str, ...]
    started_at: datetime
    ended_at: datetime | None

    @property
    def duration_seconds(self) -> int | None:
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class DayReport:
    day: date
    total_seconds: int
    entries: tuple[Entry, ...]
    running: Entry | None
    goal_minutes: int | None = None


@dataclass(frozen=True)
class WeekReport:
    start_date: date
    end_date: date
    total_seconds: int
    by_project: dict[str, int]
    by_tag: dict[str, int]
    by_project_tag: dict[str, dict[str, int]]
    entries: tuple[Entry, ...]
    daily_seconds: tuple[int, ...] = ()


@dataclass(frozen=True)
class Pomodoro:
    phase: str
    started_at: datetime
    planned_seconds: int
    entry_id: int | None

    def remaining_seconds(self, now: datetime) -> int:
        elapsed = int((now - self.started_at).total_seconds())
        return self.planned_seconds - elapsed


@dataclass(frozen=True)
class MonthReport:
    start_date: date
    end_date: date
    total_seconds: int
    by_project: dict[str, int]
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class ProjectReport:
    project: str
    total_seconds: int
    entries: tuple[Entry, ...]
    running: Entry | None
