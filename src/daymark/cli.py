"""Command-line interface for Daymark."""

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from daymark import __version__
from daymark.errors import DaymarkError
from daymark.render import (
    format_entry,
    goal_met_line,
    render_csv,
    render_day,
    render_markdown,
    render_month,
    render_project,
    render_week,
)
from daymark.store import BREAK_SECONDS, FOCUS_SECONDS, Daymark, default_db_path
from daymark.timeutil import (
    format_duration,
    format_when,
    parse_duration,
    parse_goal_minutes,
    parse_user_date,
    parse_user_time,
    utcnow,
)

EPILOG = """
examples:
  daymark init
  daymark project add writing
  daymark start writing --note "chapter 2" --tag draft
  daymark status
  daymark stop
  daymark log writing --start "2026-10-20 08:00" --duration 1h20m --note planning --tag planning
  daymark report day
  daymark report week
  daymark export csv --output week.csv
""".strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daymark",
        description=(
            "Time your own work. Daymark keeps one running timer and a SQLite "
            "history on this machine."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument("--db", help="SQLite database path. Overrides DAYMARK_DB.")
    parser.add_argument("--version", action="version", version=f"daymark {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    init = commands.add_parser("init", help="Create the local database")
    init.add_argument("--here", action="store_true", help="Create ./daymark.db in this folder")
    init.add_argument("--path", help="Create the database at this file path")

    project = commands.add_parser("project", help="Manage your projects")
    project_commands = project.add_subparsers(dest="project_cmd", required=True)
    add = project_commands.add_parser("add", help="Add a project")
    add.add_argument("name", help="Project name")
    rename = project_commands.add_parser("rename", help="Rename a project, keeping its history")
    rename.add_argument("old", help="Current name")
    rename.add_argument("new", help="New name")
    archive = project_commands.add_parser(
        "archive",
        help="Hide a project from start while keeping its history",
    )
    archive.add_argument("name", help="Project name")
    unarchive = project_commands.add_parser("unarchive", help="Make an archived project startable again")
    unarchive.add_argument("name", help="Project name")
    listing = project_commands.add_parser("list", help="List projects")
    listing.add_argument("--all", action="store_true", help="Include archived projects")

    start = commands.add_parser("start", help="Start the timer")
    start.add_argument("project", help="Project to time")
    start.add_argument("--note", default="", help="What you are doing")
    start.add_argument("--tag", action="append", dest="tags", help="Tag. Repeat for several.")

    cont = commands.add_parser("continue", help="Start the timer on your most recent project")
    cont.add_argument("--note", default="", help="What you are doing")
    cont.add_argument("--tag", action="append", dest="tags", help="Tag. Repeat for several.")

    stop = commands.add_parser("stop", help="Stop the running timer")
    stop.add_argument("--note", help="Replace the note on the open entry")
    stop.add_argument(
        "--discard",
        action="store_true",
        help="Drop the open timer and do not keep an entry",
    )

    status = commands.add_parser("status", help="Show the running timer")
    status.add_argument("--json", action="store_true", help="Print the status as JSON")

    goal = commands.add_parser("goal", help="Set a daily goal in minutes for your own work")
    goal_commands = goal.add_subparsers(dest="goal_cmd", required=True)
    goal_set = goal_commands.add_parser("set", help="Set today's target, such as 90 or 1h30m")
    goal_set.add_argument("minutes", help="Whole minutes, or a duration such as 1h30m")
    goal_commands.add_parser("show", help="Show the daily goal")
    goal_commands.add_parser("clear", help="Remove the daily goal")

    pomodoro = commands.add_parser(
        "pomodoro",
        help="Time a fixed 25 minute focus and a 5 minute break",
    )
    pomodoro_commands = pomodoro.add_subparsers(dest="pomodoro_cmd", required=True)
    pomodoro_start = pomodoro_commands.add_parser("start", help="Start a 25 minute focus")
    pomodoro_start.add_argument("project", help="Project to time")
    pomodoro_start.add_argument("--note", default="", help="What you are doing")
    pomodoro_start.add_argument("--tag", action="append", dest="tags", help="Tag. Repeat for several.")
    pomodoro_commands.add_parser("status", help="Show the focus or break countdown")
    pomodoro_commands.add_parser("break", help="Stop the focus and start a 5 minute break")
    pomodoro_commands.add_parser("done", help="Clear the break")

    log = commands.add_parser("log", help="Record a manual entry")
    log.add_argument("project", help="Project the time belongs to")
    log.add_argument("--start", required=True, help="Start time, YYYY-MM-DD HH:MM")
    log.add_argument("--end", help="End time, YYYY-MM-DD HH:MM")
    log.add_argument("--duration", help="Length instead of --end, such as 1h20m or 90m")
    log.add_argument("--note", default="", help="What the time was for")
    log.add_argument("--tag", action="append", dest="tags", help="Tag. Repeat for several.")

    edit = commands.add_parser("edit", help="Change a saved entry")
    edit.add_argument("entry_id", type=int, help="Entry id from a report")
    edit.add_argument("--project", help="Move the entry to this project")
    edit.add_argument("--note", help="Replace the note")
    edit.add_argument("--start", help="New start time")
    edit.add_argument("--end", help="New end time")

    delete = commands.add_parser("delete", help="Delete a finished entry")
    delete.add_argument("entry_id", type=int, help="Entry id from a report")

    split = commands.add_parser("split", help="Split a finished entry at a minute offset")
    split.add_argument("entry_id", type=int, help="Entry id from a report")
    split.add_argument(
        "minutes",
        type=int,
        help="Minutes after the start, where the second entry begins",
    )

    note = commands.add_parser("note", help="Set the note text on an entry")
    note.add_argument("entry_id", type=int, help="Entry id from a report")
    note.add_argument("text", nargs="*", help="Note text")
    note.add_argument("--clear", action="store_true", help="Remove the note")

    tag = commands.add_parser("tag", help="Add or remove tags on an entry")
    tag_commands = tag.add_subparsers(dest="tag_cmd", required=True)
    tag_add = tag_commands.add_parser("add", help="Attach tags")
    tag_add.add_argument("entry_id", type=int)
    tag_add.add_argument("tags", nargs="+")
    tag_remove = tag_commands.add_parser("remove", help="Detach tags")
    tag_remove.add_argument("entry_id", type=int)
    tag_remove.add_argument("tags", nargs="+")
    tag_rename = tag_commands.add_parser("rename", help="Rename a tag on every entry that uses it")
    tag_rename.add_argument("old", help="Current tag")
    tag_rename.add_argument("new", help="New tag")

    report = commands.add_parser("report", help="Summarize tracked time")
    report_commands = report.add_subparsers(dest="report_cmd", required=True)
    day = report_commands.add_parser("day", help="Entries that started on one date")
    day.add_argument("--date", help="YYYY-MM-DD. Defaults to today.")
    week = report_commands.add_parser("week", help="Group a Monday-Sunday week by project and tag")
    week.add_argument("--date", help="Any date in the week. Defaults to today.")
    month = report_commands.add_parser("month", help="Totals for one calendar month")
    month.add_argument("--date", help="YYYY-MM or YYYY-MM-DD. Defaults to this month.")
    project_report = report_commands.add_parser("project", help="Entries for one project")
    project_report.add_argument("name")
    project_report.add_argument("--from", dest="from_date", help="First date to include")
    project_report.add_argument("--to", dest="to_date", help="Last date to include")

    export = commands.add_parser("export", help="Write entries to a file or stdout")
    export_commands = export.add_subparsers(dest="export_cmd", required=True)
    csv_export = export_commands.add_parser("csv", help="Export CSV")
    csv_export.add_argument("--output", "-o", help="File to write. Omit to print.")
    markdown_export = export_commands.add_parser("markdown", help="Export Markdown")
    markdown_export.add_argument("--output", "-o", help="File to write. Omit to print.")

    backup = commands.add_parser("backup", help="Copy the SQLite database to another file")
    backup.add_argument("--output", "-o", required=True, help="Backup file to create")

    restore = commands.add_parser("restore", help="Replace the SQLite database from a backup")
    restore.add_argument("--from", dest="source", required=True, help="Backup file to restore")

    commands.add_parser("doctor", help="Check the local database for inconsistencies")
    return parser


def database_path(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db).expanduser()
    if args.command == "init" and args.path and args.here:
        raise DaymarkError("Choose either --path or --here.")
    if args.command == "init" and args.path:
        return Path(args.path).expanduser()
    if args.command == "init" and args.here:
        return Path.cwd() / "daymark.db"
    env = os.environ.get("DAYMARK_DB")
    if env:
        return Path(env).expanduser()
    if args.command == "init":
        return default_db_path()
    local = Path.cwd() / "daymark.db"
    if local.exists():
        return local
    home = default_db_path()
    if home.exists():
        return home
    raise DaymarkError(
        "No Daymark database yet. Run `daymark init` to keep it in your user folder, "
        "or `daymark init --here` to keep it in this folder."
    )


def execute(args: argparse.Namespace) -> int:
    path = database_path(args)
    if args.command != "init" and not path.exists():
        raise DaymarkError(f"No database at {path}. Run `daymark init` first.")
    with Daymark(path) as store:
        if args.command == "init":
            print(f"Database ready at {store.db_path}")
            return 0
        if args.command == "project":
            return command_project(store, args)
        if args.command == "start":
            return command_start(store, args)
        if args.command == "continue":
            return command_continue(store, args)
        if args.command == "stop":
            return command_stop(store, args)
        if args.command == "status":
            return command_status(store, args)
        if args.command == "goal":
            return command_goal(store, args)
        if args.command == "pomodoro":
            return command_pomodoro(store, args)
        if args.command == "log":
            return command_log(store, args)
        if args.command == "edit":
            return command_edit(store, args)
        if args.command == "delete":
            return command_delete(store, args)
        if args.command == "split":
            return command_split(store, args)
        if args.command == "note":
            return command_note(store, args)
        if args.command == "tag":
            return command_tag(store, args)
        if args.command == "report":
            return command_report(store, args)
        if args.command == "export":
            return command_export(store, args)
        if args.command == "backup":
            return command_backup(store, args)
        if args.command == "restore":
            return command_restore(store, args)
        if args.command == "doctor":
            return command_doctor(store)
    raise DaymarkError(f"Unknown command '{args.command}'.")


def command_project(store: Daymark, args: argparse.Namespace) -> int:
    if args.project_cmd == "add":
        project = store.add_project(args.name)
        print(f"Added project '{project.name}'.")
        return 0
    if args.project_cmd == "rename":
        project = store.rename_project(args.old, args.new)
        print(f"Renamed project to '{project.name}'.")
        return 0
    if args.project_cmd == "archive":
        project = store.archive_project(args.name)
        print(f"Archived '{project.name}'. It stays in reports and is hidden from start.")
        return 0
    if args.project_cmd == "unarchive":
        project = store.unarchive_project(args.name)
        print(f"Unarchived '{project.name}'.")
        return 0
    projects = store.list_projects(include_archived=args.all)
    if not projects:
        print("No projects yet.")
        return 0
    for project in projects:
        suffix = " [archived]" if project.archived else ""
        print(f"{project.name}{suffix}")
    return 0


def command_start(store: Daymark, args: argparse.Namespace) -> int:
    entry = store.start(args.project, note=args.note, tags=args.tags)
    print(f"Started {entry.project} at {format_when(entry.started_at)}.")
    print(format_entry(entry))
    return 0


def command_continue(store: Daymark, args: argparse.Namespace) -> int:
    entry = store.continue_latest(note=args.note, tags=args.tags)
    print(f"Continued {entry.project} at {format_when(entry.started_at)}.")
    print(format_entry(entry))
    return 0


def command_stop(store: Daymark, args: argparse.Namespace) -> int:
    if args.discard and args.note is not None:
        raise DaymarkError("Use either --note or --discard.")
    entry = store.stop(note=args.note, discard=args.discard)
    if entry is None:
        print("Discarded the running timer.")
        return 0
    print(f"Stopped {entry.project}: {format_duration(entry.duration_seconds or 0)}")
    print(format_entry(entry))
    return 0


def command_goal(store: Daymark, args: argparse.Namespace) -> int:
    if args.goal_cmd == "set":
        minutes = store.set_daily_goal(parse_goal_minutes(args.minutes))
        print(f"Daily goal set to {format_duration(minutes * 60)}.")
        return 0
    if args.goal_cmd == "clear":
        store.clear_daily_goal()
        print("Daily goal cleared.")
        return 0
    minutes = store.daily_goal_minutes()
    if minutes is None:
        print("No daily goal is set.")
        return 0
    print(f"Daily goal: {format_duration(minutes * 60)}.")
    return 0


def command_pomodoro(store: Daymark, args: argparse.Namespace) -> int:
    if args.pomodoro_cmd == "start":
        entry = store.start_pomodoro(args.project, note=args.note, tags=args.tags)
        print(f"Started a 25 minute focus on {entry.project}.")
        print(format_entry(entry))
        print(f"Break after the focus is {BREAK_SECONDS // 60} minutes.")
        return 0
    if args.pomodoro_cmd == "break":
        state = store.begin_break()
        print(f"Break started. {format_duration(state.planned_seconds)} away from the next focus.")
        return 0
    if args.pomodoro_cmd == "done":
        store.finish_pomodoro()
        print("Pomodoro cleared.")
        return 0
    return command_pomodoro_status(store)


def command_pomodoro_status(store: Daymark) -> int:
    state = store.pomodoro()
    if state is None:
        print("No pomodoro is running.")
        print(f"Focus is {FOCUS_SECONDS // 60} minutes and the break is {BREAK_SECONDS // 60} minutes.")
        return 0
    remaining = state.remaining_seconds(utcnow())
    phase = "Focus" if state.phase == "focus" else "Break"
    planned = format_duration(state.planned_seconds)
    if remaining > 0:
        print(f"{phase}: {format_duration(remaining)} left of {planned}.")
    elif remaining == 0:
        print(f"{phase} complete ({planned}).")
    else:
        print(f"{phase} complete ({planned}). Over by {format_duration(-remaining)}.")
    if state.entry_id is not None:
        print(format_entry(store.get_entry(state.entry_id)))
    return 0


def status_payload(store: Daymark) -> dict[str, object]:
    running = store.running()
    goal = store.daily_goal_minutes()
    today = store.report_day().total_seconds
    goal_seconds = None if goal is None else goal * 60
    elapsed = None
    if running is not None:
        elapsed = int((utcnow() - running.started_at).total_seconds())
        if elapsed < 0:
            elapsed = 0
    state = store.pomodoro()
    pomodoro: dict[str, object] | None = None
    if state is not None:
        pomodoro = {
            "phase": state.phase,
            "planned_seconds": state.planned_seconds,
            "remaining_seconds": state.remaining_seconds(utcnow()),
        }
    return {
        "running": running is not None,
        "entry_id": None if running is None else running.id,
        "project": None if running is None else running.project,
        "started_at": (
            None
            if running is None
            else running.started_at.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        ),
        "elapsed_seconds": elapsed,
        "note": None if running is None else running.note,
        "tags": [] if running is None else list(running.tags),
        "daily_goal_minutes": goal,
        "today_seconds": today,
        "goal_met": goal_seconds is not None and today >= goal_seconds,
        "pomodoro": pomodoro,
    }


def command_status(store: Daymark, args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(status_payload(store), indent=2, sort_keys=True))
        return 0
    running = store.running()
    if running is None:
        print("No timer is running.")
    else:
        elapsed = int((utcnow() - running.started_at).total_seconds())
        if elapsed < 0:
            elapsed = 0
        print(f"Running: {running.project}")
        print(f"Entry: {running.id}")
        print(f"Started: {format_when(running.started_at)}")
        print(f"Elapsed: {format_duration(elapsed)}")
        print(f"Note: {running.note or '(none)'}")
        print(f"Tags: {', '.join(running.tags) if running.tags else '(none)'}")
    _print_goal_line(store)
    return 0


def _print_goal_line(store: Daymark) -> None:
    line = goal_met_line(store.report_day().total_seconds, store.daily_goal_minutes())
    if line is not None:
        print(line)


def command_log(store: Daymark, args: argparse.Namespace) -> int:
    if args.end and args.duration:
        raise DaymarkError("Use either --end or --duration.")
    if not args.end and not args.duration:
        raise DaymarkError("Provide --end or --duration, for example 1h20m or 90m.")
    started = parse_user_time(args.start)
    if args.duration:
        ended = started + timedelta(seconds=parse_duration(args.duration))
    else:
        ended = parse_user_time(args.end)
    entry = store.log(
        args.project,
        started,
        ended,
        note=args.note,
        tags=args.tags,
    )
    print(f"Logged {entry.project}: {format_duration(entry.duration_seconds or 0)}")
    print(format_entry(entry))
    return 0


def command_edit(store: Daymark, args: argparse.Namespace) -> int:
    entry = store.edit(
        args.entry_id,
        project=args.project,
        note=args.note,
        started_at=parse_user_time(args.start) if args.start else None,
        ended_at=parse_user_time(args.end) if args.end else None,
    )
    print(f"Updated entry {entry.id}.")
    print(format_entry(entry))
    return 0


def command_note(store: Daymark, args: argparse.Namespace) -> int:
    if args.clear and args.text:
        raise DaymarkError("Use either note text or --clear.")
    if args.clear:
        text = ""
    elif not args.text:
        raise DaymarkError("Provide the note text, or pass --clear.")
    else:
        text = " ".join(args.text)
    entry = store.edit(args.entry_id, note=text)
    shown = entry.note or "(none)"
    print(f"Note on entry {entry.id}: {shown}")
    return 0


def command_split(store: Daymark, args: argparse.Namespace) -> int:
    first, second = store.split_entry(args.entry_id, args.minutes)
    print(f"Split entry {first.id} at {args.minutes} minutes.")
    print(format_entry(first))
    print(format_entry(second))
    return 0


def command_delete(store: Daymark, args: argparse.Namespace) -> int:
    entry = store.delete_entry(args.entry_id)
    print(f"Deleted entry {entry.id} ({entry.project}).")
    return 0


def command_tag(store: Daymark, args: argparse.Namespace) -> int:
    if args.tag_cmd == "rename":
        name, count = store.rename_tag(args.old, args.new)
        noun = "entry" if count == 1 else "entries"
        print(f"Renamed tag to '{name}' on {count} {noun}.")
        return 0
    if args.tag_cmd == "add":
        entry = store.add_tags(args.entry_id, args.tags)
    else:
        entry = store.remove_tags(args.entry_id, args.tags)
    labels = ", ".join(entry.tags) if entry.tags else "(none)"
    print(f"Entry {entry.id} tags: {labels}")
    return 0


def _parse_month(text: str):
    raw = text.strip()
    if len(raw) == 7 and raw[4] == "-":
        raw = f"{raw}-01"
    return parse_user_date(raw)


def command_report(store: Daymark, args: argparse.Namespace) -> int:
    if args.report_cmd == "day":
        day = parse_user_date(args.date) if args.date else None
        print(render_day(store.report_day(day)), end="")
        return 0
    if args.report_cmd == "week":
        day = parse_user_date(args.date) if args.date else None
        print(render_week(store.report_week(day)), end="")
        return 0
    if args.report_cmd == "month":
        day = _parse_month(args.date) if args.date else None
        print(render_month(store.report_month(day)), end="")
        return 0
    start = parse_user_date(args.from_date) if args.from_date else None
    end = parse_user_date(args.to_date) if args.to_date else None
    print(render_project(store.report_project(args.name, start=start, end=end)), end="")
    return 0


def command_export(store: Daymark, args: argparse.Namespace) -> int:
    entries = store.entries()
    if args.export_cmd == "csv":
        text = render_csv(entries)
    else:
        text = render_markdown(entries)
    if not args.output:
        print(text, end="")
        return 0
    path = Path(args.output).expanduser()
    if path.exists() and path.is_dir():
        raise DaymarkError(f"{path} is a directory.")
    if not path.parent.exists():
        raise DaymarkError(f"Folder does not exist: {path.parent}")
    try:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as exc:
        raise DaymarkError(f"Could not write {path}: {exc}") from exc
    print(f"Wrote {len(entries)} entries to {path}")
    return 0


def command_backup(store: Daymark, args: argparse.Namespace) -> int:
    path = store.backup_to(args.output)
    print(f"Backed up the database to {path}")
    return 0


def command_doctor(store: Daymark) -> int:
    problems = store.doctor()
    print(f"Database: {store.db_path}")
    if not problems:
        print("daymark doctor: ok")
        return 0
    for problem in problems:
        print(f"problem: {problem}")
    print("daymark doctor: found problems")
    return 1


def command_restore(store: Daymark, args: argparse.Namespace) -> int:
    path = store.restore_from(args.source)
    print(f"Restored the database at {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except DaymarkError as exc:
        print(f"daymark: {exc}", file=sys.stderr)
        return 1


def console_main() -> None:
    sys.exit(main())
