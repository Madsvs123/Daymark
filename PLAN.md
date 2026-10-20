# Further local timer work

Daymark stays a timer for the operator's own work. The database stays a SQLite file on this machine. Nothing in this list adds accounts, a shared database, or a record of anyone else's time.

## Timing

- Warn in `status` when the open timer started on an earlier calendar day.
- Add `round ID` to move a finished entry's start and end to the nearest minute, and refuse the change when that would overlap another entry.
- Add `undo` for the most recent stop, putting that entry back into the open timer when nothing else is running.

## Projects, tags, and notes

- Remember default tags on a project and apply them when a timer starts, still editable on that entry.
- Add `tag list` so the names already stored in this database can be printed without scanning a report.
- Add `note ID --append TEXT` so a later remark can be added without replacing the existing note.
- Add `search TEXT` to list entries whose note contains that text.

## Reports and files

- Add `report year` that sums each calendar month the way `report month` sums each project.
- Add a text sparkline to the month report, using the same blocks as the week.
- Let `export csv` and `export markdown` take `--from` and `--to`.
- Show progress toward the daily goal in `status` before the goal is met. Keep the current line once it is met.

## Recovery

- Teach `doctor --fix` to rebuild a missing open-timer row when exactly one entry is unfinished, and to do nothing else unless the operator asks.
- Document a manual backup habit: run `backup` before `restore`, and keep the copy next to the database only when the operator chooses that folder.

## Out of scope

Accounts, hosted sync, and timers for other people stay out of the tool.
