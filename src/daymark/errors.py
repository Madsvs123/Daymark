"""Failures the operator can correct."""


class DaymarkError(Exception):
    """An expected problem, shown as `daymark: ...`."""


class TimerAlreadyRunning(DaymarkError):
    """A second timer was requested while one is still open."""


class NoRunningTimer(DaymarkError):
    """Stop was requested and nothing is open."""


class ProjectNotFound(DaymarkError):
    """The named project is not in this database."""


class ProjectExists(DaymarkError):
    """A project with that name is already stored."""


class ProjectArchived(DaymarkError):
    """The project is archived, so a new timer cannot start on it."""


class EntryNotFound(DaymarkError):
    """The entry id is not in this database."""


class InvalidInterval(DaymarkError):
    """The end of an entry is not after its start."""


class OverlappingEntry(DaymarkError):
    """The interval crosses another saved entry."""
