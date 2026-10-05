# Work board

Control desk: the main Claude session. Tasks are typed there, handed to background agents (one worktree + branch each), checked, then merged into `develop` one at a time.

| # | Task | Branch | State | Proof | Waiting on |
| --- | --- | --- | --- | --- | --- |
| 1 | Monthly shift rotation, allowed only between `NGI 6 AM - 2 PM` and `NGI 12 PM - 8 PM` | `task-1-shift-rotation` (63c2460, 1d52950) | merged into local develop 2026-10-01 (unpushed); patch run on avinas1 | 13 server tests pass on nepalgas; patch ticked the two NGI shifts on avinas1; preview lists 54 staff; dialog not yet clicked through | developer: try the screen on localhost |

## Done earlier (2026-09-30, commit 70d1318 on develop)

- Monthly Attendance BS: IN/OUT from the day's first and last punch; O.T. only on submitted Overtime Sheet days.

| # | Task | Branch | State | Proof | Waiting on |
| --- | --- | --- | --- | --- | --- |
| 1b | Rotation dialog fixes: company bug, two-way Nepali date | develop 7f9a47f (local, unpushed) | done | used on avinas1 2026-10-01: 59 assignments | developer: keep or undo those 59 |
| 2 | Shift Roster: employees × BS months grid, paint shifts, coverage strip, staged Apply | `task-2-shift-roster` (94bed50, 871ccef, 6f8af19) | merged into local develop 2026-10-05 (unpushed) | 23 rotation tests pass on nepalgas; Apply now sends bounded periods (`set_periods`), JS syntax-checked; page not yet clicked in a browser | developer: try /app/shift-roster on localhost |
