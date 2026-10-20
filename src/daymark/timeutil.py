"""Time parsing, storage format, and calendar windows."""

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from daymark.errors import DaymarkError

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_DURATION_RE = re.compile(r"^(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?$")
_FAR_FUTURE = datetime(9999, 12, 31, tzinfo=timezone.utc)


def local_timezone() -> tzinfo:
    current = datetime.now().astimezone().tzinfo
    return current if current is not None else timezone.utc


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DaymarkError("A time value needs a timezone.")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def iso(value: datetime) -> str:
    """Fixed-width UTC text so SQLite can compare timestamps as strings."""
    return ensure_utc(value).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def parse_stored(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def parse_user_time(text: str, tz: tzinfo | None = None) -> datetime:
    raw = text.strip()
    if not raw:
        raise DaymarkError("A time value is required.")
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise DaymarkError(f"Could not read time '{text}'. Use YYYY-MM-DD HH:MM.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz or local_timezone())
    return ensure_utc(parsed)


def parse_duration(text: str) -> int:
    """Return seconds for a duration such as `1h20m`, `90m`, or `45s`."""
    raw = "".join(text.strip().lower().split())
    if not raw:
        raise DaymarkError("A duration is required.")
    match = _DURATION_RE.fullmatch(raw)
    if match is None or not any(match.group(part) for part in ("hours", "minutes", "seconds")):
        raise DaymarkError(f"Could not read duration '{text}'. Use a value like 1h20m or 90m.")
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise DaymarkError("A duration must be greater than zero.")
    return total


def parse_goal_minutes(text: str) -> int:
    """Minutes for a daily goal: a whole number, or a duration such as 1h30m."""
    raw = text.strip()
    if not raw:
        raise DaymarkError("A daily goal is required.")
    if raw.isdigit():
        minutes = int(raw)
    else:
        seconds = parse_duration(raw)
        if seconds % 60 != 0:
            raise DaymarkError("A daily goal is a whole number of minutes, such as 90 or 1h30m.")
        minutes = seconds // 60
    if minutes < 1:
        raise DaymarkError("A daily goal must be at least 1 minute.")
    if minutes > 24 * 60:
        raise DaymarkError("A daily goal must be at most 1440 minutes.")
    return minutes


def parse_user_date(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError as exc:
        raise DaymarkError(f"Could not read date '{text}'. Use YYYY-MM-DD.") from exc


def format_when(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def format_duration(seconds: int) -> str:
    sign = "-" if seconds < 0 else ""
    remaining = abs(int(seconds))
    hours, rest = divmod(remaining, 3600)
    minutes, secs = divmod(rest, 60)
    if secs:
        return f"{sign}{hours}h {minutes:02d}m {secs:02d}s"
    return f"{sign}{hours}h {minutes:02d}m"


def day_window(day: date, tz: tzinfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start.replace(microsecond=0), end.replace(microsecond=0)


def week_window(day: date, tz: tzinfo) -> tuple[datetime, datetime, date, date]:
    """Monday-Sunday week that contains `day`, in `tz`."""
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    start, _ = day_window(monday, tz)
    _, end = day_window(sunday, tz)
    return start, end, monday, sunday


def intervals_overlap(
    start_a: datetime,
    end_a: datetime | None,
    start_b: datetime,
    end_b: datetime | None,
) -> bool:
    """Half-open overlap. A missing end means the timer is still running."""
    finish_a = end_a or _FAR_FUTURE
    finish_b = end_b or _FAR_FUTURE
    return start_a < finish_b and start_b < finish_a


def normalize_project_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 60:
        raise DaymarkError("A project name needs 1 to 60 characters.")
    if any(ord(char) < 32 or char in "\\/" for char in cleaned):
        raise DaymarkError("A project name cannot include slashes or control characters.")
    return cleaned


def normalize_note(note: str | None) -> str:
    if note is None:
        return ""
    cleaned = " ".join(note.replace("\x00", "").split())
    if len(cleaned) > 500:
        raise DaymarkError("Notes can be at most 500 characters.")
    return cleaned


def normalize_tags(tags: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not tags:
        return ()
    cleaned: list[str] = []
    for raw in tags:
        name = raw.strip().lower()
        if not name:
            raise DaymarkError("A tag cannot be blank.")
        if _TAG_RE.fullmatch(name) is None:
            raise DaymarkError(
                f"Tag '{raw}' may use letters, numbers, hyphens, and underscores, "
                "and must start with a letter or number."
            )
        if name not in cleaned:
            cleaned.append(name)
    return tuple(sorted(cleaned))
