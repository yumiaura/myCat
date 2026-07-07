# Activity diary & focus sessions

mycat keeps a private, local-only diary of your day - how much you move the
mouse, how many keys you press, when you focus and when you rest - and shows
it in the **Activity** dialog (right-click the cat → Activity…).

---

## Privacy rules (hard guarantees)

1. **Counters, never content.** The keyboard hook increments an integer and
   discards the key identity inside the callback - nothing that could
   reconstruct what you typed is ever stored. The mouse contributes a
   travelled *distance*, never a trajectory.
2. **Local only.** Everything lands in one SQLite file on this computer and
   participates in no network request of any kind. There is no mechanism to
   send it anywhere.
3. **You own it.** A retention limit trims old data automatically, the
   *Delete all recorded data…* button wipes everything, and both tracking
   switches can be turned off at any time.

## What is recorded

Two tables in `activity.db` (Linux: `~/.local/share/mycat/`, macOS:
`~/Library/Application Support/mycat/`, Windows: `%LOCALAPPDATA%\mycat\`):

| Table | One row per | Fields |
|---|---|---|
| `minute_activity` | minute | cursor path (px), key count, click count, active flag |
| `focus_session` | pomodoro phase | kind (focus/break/long_break), start, end, planned length, completed |

The database uses a durable rollback journal (`synchronous=FULL`): every
commit lands in the main file immediately, so an abrupt shutdown cannot lose
recorded history. The in-progress minute is flushed on a clean Quit.

## How collection works

Two independent tiers:

- **Tier 1 - cursor (no hooks, no OS permissions).** The cursor position is
  polled 10× per second; the Euclidean distance between consecutive samples
  is accumulated into the current minute.
- **Tier 2 - keys and clicks (global counts).** Via `pynput` on Windows/macOS,
  or a pure-Python `python-xlib` backend on Linux/X11. Key presses and mouse
  clicks are *counted*. Where neither can run (e.g. Wayland, missing macOS Input
  Monitoring permission) this tier silently degrades and only the cursor tier
  keeps recording.

The dialog has three nested checkboxes: **Enable Activity** (master), and under
it **Enable Mouse** (click count) and **Enable Keyboard** (key count). All on by
default; the sub-tracks grey out while Activity is off. The tier-1 cursor path
always records while Activity is on - the cat's eyes track the cursor anyway -
so only the two *counts* are switchable.

### When is a minute "active"?

A minute is **active** if any of these happened in it:

- cursor path ≥ **30 px** (`ACTIVE_MOUSE_PX_THRESHOLD` - filters out a bumped
  desk), or
- ≥ 1 key press, or
- ≥ 1 click.

Otherwise it is a **rest** minute. Note the honest limitation: a minute of
reading or thinking with zero input counts as rest - the diary measures
*input*, not *work*.

## The period model: Focus / Break / Other

Every row in the Activity table is a *period*, and there are exactly three
kinds:

| Label | Meaning |
|---|---|
| 🍅 **Focus** | A pomodoro focus phase (completed or stopped early). |
| ☕ **Break** | A pomodoro break (short or the long one after every 4 focuses). |
| ▷ **Other** | Activity **without a running timer** - contiguous active minutes outside any pomodoro window, with gaps under 5 min merged into one period. |

The **live current period** is the top row (italic, ▶): during a pomodoro it
is ▶ Focus / ▶ Break; otherwise the ongoing activity run shows as ▶ Other.
Its Duration cell shows the elapsed time so far and its counters update every
second. The current period survives an app restart - it is reconstructed
from the recorded minutes, not from memory.

The bottom **TOTAL** row (`TOTAL 🍅 N` - N is the number of *completed*
pomodoros) is the sum of the rows above it, by construction: keys, clicks
and cursor path always reconcile.

## The timeline strip

A per-minute heat map of the **full day** (midnight → midnight):

- **white** - time passed, but nothing was tracked;
- **green** - tracked, no activity (rest);
- **red** - tracked, active; the deeper the red, the busier the minute;
- **grey** - hasn't happened yet (the future);
- **blue line with a triangle** - now.

Hour marks run along the bottom (thinned to every 2–3 h). Hovering shows the
time under the cursor.

## The formulas

### Active %

```
active % = active minutes in the period / period length in minutes × 100
```

For a focus phase, high is good (you stayed with it). For a break, low is
good (you actually stepped away). "Other" periods are built *from* active
minutes, so their percentage is high by construction - only the merged
sub-5-minute gaps dilute it.

### Cursor distance

Per sample pair: `√(Δx² + Δy²)` pixels, summed per minute. Displayed as a
physical distance via the primary screen's DPI:

```
meters = pixels / DPI × 0.0254
```

(at 96 DPI, 1 km ≈ 3.78 million px). Caveats: 10 Hz sampling straightens
fast curves (a lower bound); the result is centimetres *on the glass*, not
mousepad travel; multi-monitor setups use the primary screen's DPI.

### Red saturation (timeline heat)

Each active minute gets a busy score on one scale:

```
score = keys + clicks × 5 + pixels / 100      (full saturation at 300)
```

A click weighs ≈5 keys; 100 px of travel ≈ 1 key. 300 points - e.g. 300
keys/min, or 60 clicks, or 100 keys + 20 clicks + 10,000 px - is the deepest
red; more is clamped. The colour is a linear blend from pale `rgb(233,179,179)`
to deep `rgb(192,57,43)`. Rest minutes are a fixed green (intensity is
meaningless for rest). The still-unflushed current minute is drawn at a
minimum 12% so fresh input is visible immediately.

## Pomodoro & auto-pomodoro

Classic cycle: **25 min focus → 5 min break**, and after every 4 focuses a
**15-min long break** (all four durations configurable). During focus the cat
keeps still and non-urgent banners are held until the break; calendar
reminders still fly through. Hovering the cat shows the current period -
"Focus · 17:42 left · …" during a session, or "Other · 32 min · ⌨ … · 96%
active" when you're working without a timer.

**Auto-start:** returning to the keyboard after ≥ 5 minutes of silence
(`IDLE_RESUME_MINUTES`) quietly starts a focus countdown - no banner, just
the bar and tooltip. An explicit *Stop* blocks auto-starts for one break
length ("not now" is respected), and launching the app never auto-starts a
session by itself.

## Morning digest

The first time the cat sees you after 05:00 it flies one banner with
yesterday's numbers - cursor km, key count, completed 🍅 and the longest
focus. Once per day; an empty yesterday is skipped silently.

## Configuration reference

`~/.config/mycat/config.ini`:

```ini
[activity]
enabled = true            ; master switch (Tier 1 + recording)
keyboard_enabled = true   ; Tier 2: key/click counting
retention_days = 90       ; minute history kept this long

[focus]
focus_minutes = 25
break_minutes = 5
long_break_minutes = 15   ; the long break (use 15–30 to taste)
sessions_before_long_break = 4
auto_start = true         ; auto-pomodoro on input-after-idle
```

Tuning constants (in code):

| Constant | Where | Default | Meaning |
|---|---|---|---|
| `ACTIVE_MOUSE_PX_THRESHOLD` | `activity.py` | 30 | px/min for a minute to count as active |
| `IDLE_RESUME_MINUTES` | `activity.py` | 5 | silence that ends a period / triggers auto-start |
| `SAMPLE_MOVE_EPSILON_PX` | `activity.py` | 3 | per-sample noise floor for input detection |
| `BUSY_FULL` | `activity_ui.py` | 300 | busy score for full red saturation |
| `CURSOR_POLL_MS` | `activity.py` | 100 | cursor sampling period (10 Hz) |
