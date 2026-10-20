"""Text, CSV, and Markdown views of stored entries."""

import csv
import io

from daymark.models import DayReport, Entry, MonthReport, ProjectReport, WeekReport
from daymark.timeutil import format_duration, format_when


def goal_met_line(today_seconds: int, goal_minutes: int | None) -> str | None:
    """A single status line once completed time reaches the daily goal."""
    if goal_minutes is None:
        return None
    goal_seconds = goal_minutes * 60
    if today_seconds < goal_seconds:
        return None
    return (
        f"Daily goal met: {format_duration(today_seconds)} of {format_duration(goal_seconds)}."
    )


def format_entry(entry: Entry) -> str:
    start = format_when(entry.started_at)
    if entry.ended_at is None:
        span = f"{start}  running"
        duration = "running"
    else:
        span = f"{start}  {format_when(entry.ended_at)}"
        duration = format_duration(entry.duration_seconds or 0)
    tags = ", ".join(entry.tags) if entry.tags else "untagged"
    note = f"  {entry.note}" if entry.note else ""
    return f"#{entry.id}  {entry.project}  {span}  {duration}  [{tags}]{note}"


def render_day(report: DayReport) -> str:
    lines = [report.day.isoformat(), ""]
    if not report.entries and report.running is None:
        lines.append("No completed entries.")
    for entry in report.entries:
        lines.append(format_entry(entry))
    if report.running is not None:
        lines.append(format_entry(report.running))
        lines.append("This timer is still running and is not included in the total.")
    lines.append("")
    lines.append(f"Total: {format_duration(report.total_seconds)}")
    met = goal_met_line(report.total_seconds, report.goal_minutes)
    if met is not None:
        lines.append(met)
    return "\n".join(lines) + "\n"


_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: tuple[int, ...] | list[int]) -> str:
    """One character per day. A dot is a day with no completed time."""
    if not values:
        return ""
    peak = max(values)
    if peak <= 0:
        return "·" * len(values)
    chars: list[str] = []
    for value in values:
        if value <= 0:
            chars.append("·")
            continue
        index = round((value / peak) * (len(_SPARK_BLOCKS) - 1))
        chars.append(_SPARK_BLOCKS[index])
    return "".join(chars)


def render_week(report: WeekReport) -> str:
    days = report.daily_seconds or (0, 0, 0, 0, 0, 0, 0)
    lines = [
        f"Week of {report.start_date.isoformat()} to {report.end_date.isoformat()}",
        f"Daily sparkline (Mon-Sun): {sparkline(days)}",
        "",
        "By project and tag",
    ]
    if not report.entries:
        lines.append("  No completed entries.")
    for project in sorted(report.by_project, key=str.lower):
        lines.append(f"  {project}")
        tags = report.by_project_tag.get(project, {})
        for tag in _ordered_tags(tags):
            label = tag or "(untagged)"
            lines.append(f"    {label}: {format_duration(tags[tag])}")
        lines.append(f"    total: {format_duration(report.by_project[project])}")
    lines.append("")
    lines.append("By tag")
    if not report.by_tag:
        lines.append("  No completed entries.")
    else:
        for tag in _ordered_tags(report.by_tag):
            label = tag or "(untagged)"
            lines.append(f"  {label}: {format_duration(report.by_tag[tag])}")
    lines.append("")
    lines.append(f"Week total: {format_duration(report.total_seconds)}")
    lines.append(
        "Tag lines count an entry once for each of its tags. "
        "Project totals and the week total count each entry once."
    )
    return "\n".join(lines) + "\n"


def render_month(report: MonthReport) -> str:
    lines = [
        f"Month of {report.start_date.isoformat()} to {report.end_date.isoformat()}",
        "",
        "By project",
    ]
    if not report.entries:
        lines.append("  No completed entries.")
    for project in sorted(report.by_project, key=str.lower):
        lines.append(f"  {project}: {format_duration(report.by_project[project])}")
    lines.append("")
    lines.append(f"Entries: {len(report.entries)}")
    lines.append(f"Month total: {format_duration(report.total_seconds)}")
    return "\n".join(lines) + "\n"


def render_project(report: ProjectReport) -> str:
    lines = [f"Project: {report.project}", ""]
    if not report.entries and report.running is None:
        lines.append("No completed entries.")
    for entry in report.entries:
        lines.append(format_entry(entry))
    if report.running is not None:
        lines.append(format_entry(report.running))
        lines.append("This timer is still running and is not included in the total.")
    lines.append("")
    lines.append(f"Entries: {len(report.entries)}")
    lines.append(f"Total: {format_duration(report.total_seconds)}")
    return "\n".join(lines) + "\n"


def render_csv(entries: list[Entry]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "id",
            "project",
            "note",
            "tags",
            "started_at",
            "ended_at",
            "duration_seconds",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "id": entry.id,
                "project": entry.project,
                "note": entry.note,
                "tags": ";".join(entry.tags),
                "started_at": entry.started_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "ended_at": (
                    entry.ended_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    if entry.ended_at is not None
                    else ""
                ),
                "duration_seconds": (
                    "" if entry.duration_seconds is None else str(entry.duration_seconds)
                ),
            }
        )
    return buffer.getvalue()


def render_markdown(entries: list[Entry]) -> str:
    totals: dict[str, int] = {}
    for entry in entries:
        if entry.duration_seconds is None:
            continue
        totals[entry.project] = totals.get(entry.project, 0) + entry.duration_seconds
    lines = [
        "# Daymark export",
        "",
        "Local record of the operator's own tracked work.",
        "",
        "## Totals by project",
        "",
    ]
    if not totals:
        lines.append("No completed entries.")
    else:
        for project in sorted(totals, key=str.lower):
            lines.append(f"- {project}: {format_duration(totals[project])}")
    lines.append("")
    lines.append(f"**Total completed:** {format_duration(sum(totals.values()))}")
    lines.append("")
    lines.append("## Entries")
    lines.append("")
    lines.append("| ID | Project | Start | End | Duration | Tags | Note |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for entry in entries:
        end = entry.ended_at.strftime("%Y-%m-%dT%H:%M:%S+00:00") if entry.ended_at else ""
        duration = (
            format_duration(entry.duration_seconds) if entry.duration_seconds is not None else ""
        )
        lines.append(
            "| {id} | {project} | {start} | {end} | {duration} | {tags} | {note} |".format(
                id=entry.id,
                project=_md_cell(entry.project),
                start=entry.started_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                end=end,
                duration=duration,
                tags=_md_cell(", ".join(entry.tags)),
                note=_md_cell(entry.note),
            )
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _ordered_tags(keys: dict[str, int]) -> list[str]:
    named = sorted((key for key in keys if key), key=str.lower)
    if "" in keys:
        named.append("")
    return named


def _md_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|")
