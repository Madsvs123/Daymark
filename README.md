# Daymark

Daymark is a local command-line timer for work you do yourself. It keeps one running timer, plus projects, notes, and tags, in a SQLite file on your machine. You choose whether that file lives in your user folder or in a project folder. Daymark does not upload the database.

Source: https://github.com/Madsvs123/Daymark

## Install

From a checkout of this repository:

```powershell
py -3 -m pip install -e .
daymark --help
```

Without installing the console script, from the repository root:

```powershell
$env:PYTHONPATH = "src"
py -3 -m daymark --help
```

Daymark needs Python 3.10 or newer. The standard library is enough; the only dependency for development is pytest.

## Where the data lives

| How you create it | Database file |
| --- | --- |
| `daymark init` | `%USERPROFILE%\.daymark\daymark.db` |
| `daymark init --here` | `.\daymark.db` in the current folder |
| `daymark init --path C:\notes\daymark.db` | The path you give |

Later commands look for a database in this order:

1. `--db PATH` on the command line
2. The `DAYMARK_DB` environment variable
3. `.\daymark.db`, when that file is in the current folder
4. `%USERPROFILE%\.daymark\daymark.db`

`--db` and `DAYMARK_DB` point at a file. Create it with `daymark init` before starting a timer. `daymark backup -o FILE` writes a consistent copy and refuses to overwrite a file that is already there. `daymark restore --from FILE` replaces the current database with that copy. The source has to be a Daymark SQLite file.

## A normal day

Create a database once, add the projects you actually switch between, and start a timer when you begin:

```powershell
daymark init
daymark project add writing
daymark project rename writing drafts
daymark project add reading
daymark start writing --note "chapter 2" --tag draft
```

Close the terminal whenever you need to. The open timer stays in the database. Come back and check it, then stop it when you switch tasks:

```powershell
daymark status
daymark stop
daymark start reading --note "source notes" --tag research
```

If you started the wrong project, drop the open timer:

```powershell
daymark stop --discard
```

If you forgot to start, write the block in afterward. Times without a timezone are read in your local time. You can also pass an ISO timestamp such as `2026-10-20T08:00:00+03:00`.

```powershell
daymark log writing --start "2026-10-20 08:00" --end "2026-10-20 08:40" --note "planning" --tag planning
daymark log writing --start "2026-10-20 09:00" --duration 1h20m --note "draft"
```

Reports print entry ids. Use those ids to fix a note, move an entry, or retag it:

```powershell
daymark report day
daymark edit 3 --note "planning the outline" --project writing
daymark tag add 3 outline
daymark tag remove 3 planning
```

At the end of the day, or at the end of the week, read the totals and keep a copy:

```powershell
daymark report day
daymark report week
daymark report project writing
daymark export csv --output week.csv
daymark export markdown --output week.md
```

`report day` and `report week` default to today. Pass `--date 2026-10-20` to ask about another day, or about the Monday–Sunday week that contains that date. `report project` accepts `--from` and `--to` as inclusive dates.

An entry belongs to the day and week in which it started. A timer that is still running is shown, and it is left out of the totals until you stop it.

## How a week report adds up

`daymark report week` groups completed time by project, and under each project by tag. It also prints a tag summary, a text sparkline of the seven days (Monday through Sunday), and one week total. A dot in the sparkline is a day with no completed time. The tallest block is the busiest day that week.

A block with two tags is listed under each tag. The project total and the week total count that block once, so the tag lines can add up to more than the week total. The report says so under the total. Untagged time is listed as `(untagged)`. In the sample below, the block started on Friday, so that day is the tallest mark.

```
Week of 2026-10-19 to 2026-10-25
Daily sparkline (Mon-Sun): ····█··

By project and tag
  writing
    draft: 2h 00m
    total: 2h 00m

By tag
  draft: 2h 00m

Week total: 2h 00m
Tag lines count an entry once for each of its tags. Project totals and the week total count each entry once.
```

## Commands

| Command | What it does |
| --- | --- |
| `daymark init [--here \| --path FILE]` | Create the SQLite database |
| `daymark project add NAME` | Add a project |
| `daymark project rename OLD NEW` | Rename a project without moving its history |
| `daymark project archive NAME` | Hide a project from start; keep its entries in reports |
| `daymark project unarchive NAME` | Make an archived project startable again |
| `daymark project list [--all]` | List projects you can start, or every project |
| `daymark start PROJECT [--note TEXT] [--tag TAG]` | Start the single running timer |
| `daymark stop [--note TEXT] [--discard]` | Stop the timer, or drop it |
| `daymark status` | Show the open timer and how long it has run |
| `daymark goal set MINUTES` | Set a daily goal, as minutes or a duration such as `1h30m` |
| `daymark goal show` | Show the daily goal |
| `daymark goal clear` | Remove the daily goal |
| `daymark pomodoro start PROJECT [--note TEXT] [--tag TAG]` | Start a fixed 25 minute focus |
| `daymark pomodoro status` | Show the focus or break countdown |
| `daymark pomodoro break` | Stop the focus and start a 5 minute break |
| `daymark pomodoro done` | Clear the break |
| `daymark log PROJECT --start TIME (--end TIME \| --duration DURATION) [--note TEXT] [--tag TAG]` | Record a finished block |
| `daymark edit ID [--project NAME] [--note TEXT] [--start TIME] [--end TIME]` | Change a saved entry |
| `daymark delete ID` | Delete a finished entry |
| `daymark split ID MINUTES` | Split a finished entry at a minute offset from its start |
| `daymark note ID TEXT` | Set the note text on an entry |
| `daymark note ID --clear` | Remove the note from an entry |
| `daymark tag add ID TAG [TAG ...]` | Attach tags |
| `daymark tag remove ID TAG [TAG ...]` | Detach tags |
| `daymark tag rename OLD NEW` | Rename a tag on every entry that uses it |
| `daymark report day [--date DATE]` | Entries and a total for one date |
| `daymark report week [--date DATE]` | Project and tag totals for a week |
| `daymark report month [--date DATE]` | Project totals for a calendar month |
| `daymark report project NAME [--from DATE] [--to DATE]` | Entries for one project |
| `daymark export csv [-o FILE]` | CSV of every entry |
| `daymark export markdown [-o FILE]` | Markdown summary and table |
| `daymark backup -o FILE` | Copy the SQLite file to a new path |
| `daymark restore --from FILE` | Replace the current database with a backup |

`--duration` accepts `1h20m`, `90m`, `2h`, `45s`, and combinations such as `1h20m30s`. Spaces are ignored. Use it instead of `--end`.

A daily goal is a minute target for your own completed time. It lives in the same SQLite file. When today's finished entries reach that target, `daymark status` and `daymark report day` add one line. A timer that is still running does not count toward the goal.

```powershell
daymark goal set 90
daymark goal set 1h30m
daymark goal show
daymark status
```

A pomodoro is the same local timer with a fixed length: 25 minutes of focus, then 5 minutes of break. It is not configurable, and it stays in the SQLite file.

```powershell
daymark pomodoro start writing --note "chapter 2"
daymark pomodoro status
daymark pomodoro break
daymark pomodoro done
```

Only one timer can run at a time. Starting another project while one is open is refused until you stop or discard the open timer. A manual entry that crosses an existing block is refused too. Adjacent blocks are fine: one may end at the same minute the next one starts.

CSV columns are `id`, `project`, `note`, `tags`, `started_at`, `ended_at`, and `duration_seconds`. Tags are separated with `;`. Times in the file are UTC. Omit `-o` to print the export to the terminal.

Tag names use letters, numbers, hyphens, and underscores. Project names can contain spaces. Notes can be up to 500 characters.

## Development

```powershell
py -3 -m pip install -e ".[dev]"
py -3 -m pytest
```

The tests use a temporary SQLite file. They cover start/stop duration across separate openings of the database, rejection of a second open timer, week totals by project and tag, and CSV export.

## License

MIT License. Copyright (c) 2026 Madsvs123. See [LICENSE](LICENSE).
