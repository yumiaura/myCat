# mycat interactive char-pack format

A character is a single `<name>.zip`. The cat is a small **state machine**: a base
"awake" pose whose pupils follow the cursor, plus optional expressions and
animations that play on idle, on click, on wake/sleep, and on low battery.

Everything is **convention over configuration**: you drop files with the
reserved names below into the zip and they are picked up automatically. Anything
missing simply disables that behaviour — so a character can be as small as one PNG and
grow incrementally. `config.json` only carries *parameters* (timings, pupil
geometry, thresholds), never file paths.

All images are RGBA with a transparent background. Coordinates in `config.json`
are in **`static.png` native pixels**; the runtime scales the character
proportionally to fit within `max_width` × `max_height` (default 200×400,
downscale-only) and scales everything else by the same factor.

---

## File-naming standard

Files live at the **root of the zip** (no subfolders). Reserved names:

### Required
| File | Type | Drives |
|------|------|--------|
| `static.png` | still | The awake/idle body. Eyes drawn as open sockets where pupils show. |
| `config.json` | json | Parameters (see below). |

### Eyes (optional, but the whole point)
| File | Type | Drives |
|------|------|--------|
| `eye_left.png` | still | Left pupil sprite, drawn over the open socket, moving toward the cursor. |
| `eye_right.png` | still | Right pupil sprite. |

Pupils only render when both sprites **and** `config.eyes` are present.

### Expression stills (optional)
| File | Type | Drives |
|------|------|--------|
| `blink.png` | still | Eyes closed — shown for the periodic blink and the click squint. |
| `sleep.png` | still | The sleeping pose, held for the whole sleep state. |

### Transition animations — play **once**, then settle (optional)
| File | Type | Plays when | Settles to |
|------|------|-----------|-----------|
| `sleep_in.gif` | anim | entering sleep (long idle) | `sleep.png` |
| `sleep_out.gif` | anim | waking (interaction while asleep) | `static.png` |
| `yawn.gif` | anim | cursor still for `idle.yawn_after` | `static.png` |

### Reaction pools — play **once**, picked at random (optional)
Numbered sets; the runtime globs `<role><n>.gif` (`n` ≥ 1) and picks one at random.
| Pattern | Plays when |
|---------|-----------|
| `idle1.gif`, `idle2.gif`, … | spontaneously while awake, every `idle.random_every` |
| `click1.gif`, `click2.gif`, … | the cat is clicked (falls back to the `blink.png` squint if none) |
| `hungry1.gif`, `hungry2.gif`, … | battery is low — "feed me", every `battery.every` |

> Conventions: lowercase names, role prefix, optional integer index for pools,
> `.png` for stills, `.gif` for animations. Unknown files are ignored.

---

## `config.json`

Every section is optional. Coordinates are in `static.png` native pixels.

```jsonc
{
  "name": "cat",
  "max_width": 200,                  // scale to fit this box, proportionally,
  "max_height": 400,                 // downscale-only (default 200x400)

  "eyes": {
    "travel_radius": 28,             // how far a pupil moves from its centre
    "left":  { "x": 559, "y": 433 }, // pupil rest centre on static.png
    "right": { "x": 693, "y": 433 }
  },

  "blink":  { "enabled": true, "every": [3, 7], "duration": 0.28 },
  "click_squint": 0.5,               // hold blink.png this long on click

  "idle": {
    "yawn_after":  60,               // s with no cursor MOVEMENT -> yawn.gif
    "sleep_after": 300,              // s with no INTERACTION -> sleep (~5 min)
    "random_every": [25, 60]         // random gap between idleN.gif
  },

  "battery": {
    "hungry_below": 20,              // percent -> hungry state
    "every": [30, 60]               // gap between hungryN.gif while low
  }
}
```

Defaults if omitted: blink on when `blink.png` exists; `yawn_after` 60,
`sleep_after` 300, `random_every` [25, 60]; battery `hungry_below` 20.

---

## State machine

One state is active at a time. Highest applicable wins:

```
hungry  >  sleep  >  yawn  >  reaction (idle/click)  >  blink  >  awake
```

- **awake** — `static.png` + pupils tracking the cursor. The resting state.
- **blink** — `blink.png` for `blink.duration`, every `blink.every`. (No pupils.)
- **click** — on click: a random `clickN.gif` once, else `blink.png` for
  `click_squint`. Resets the idle timers.
- **reaction (idle random)** — every `idle.random_every`, a random `idleN.gif`
  once, then back to awake.
- **yawn** — cursor hasn't moved for `idle.yawn_after`: `yawn.gif` once, then
  awake. A precursor to sleep.
- **sleep** — no interaction (move/click) for `idle.sleep_after` (~5 min):
  `sleep_in.gif` once → hold `sleep.png`. Pupils do not track while asleep.
  Any interaction → `sleep_out.gif` once → awake.
- **hungry** — while battery ≤ `battery.hungry_below`: a random `hungryN.gif`
  every `battery.every`, then back to the underlying state. (Battery is read
  natively where available; on a desktop with no battery this never triggers.)

"Interaction" = mouse move over the cat, drag, or click. "Cursor movement" for
`yawn_after` is global cursor motion.

---

## Graceful degradation (author incrementally)

| You ship | You get |
|----------|---------|
| `static.png` + `config.json` | a static cat (draggable, all app chrome) |
| + `eye_left/right.png` + `config.eyes` | pupils follow the cursor |
| + `blink.png` | periodic blink + squint on click |
| + `sleep.png` + `sleep_in.gif` + `sleep_out.gif` | sleeps after ~5 min idle, wakes on interaction |
| + `yawn.gif` | yawns after ~1 min of a still cursor |
| + `idleN.gif` | spontaneous idle animations |
| + `clickN.gif` | richer click reactions |
| + `hungryN.gif` | "feed me" when the battery is low |

---

## Examples

**Minimal** (today's behaviour):
```
cat.zip
├── static.png
├── blink.png
├── eye_left.png
├── eye_right.png
└── config.json        # name, max_width, max_height, eyes, blink, click_squint
```

**Full**:
```
cat.zip
├── static.png   blink.png   sleep.png
├── eye_left.png eye_right.png
├── sleep_in.gif sleep_out.gif yawn.gif
├── idle1.gif idle2.gif
├── click1.gif click2.gif
├── hungry1.gif
└── config.json
```

---

## Implementation status

The full state machine is **live** (`mycat/char_pack.py` + `PixelCatWindow`):
awake (cursor-tracking pupils), blink, click reaction (`clickN.gif` or squint),
idle-random (`idleN.gif`), yawn, sleep (`sleep_in/out` + held `sleep.png`), and
hungry (`hungryN.gif` on low battery), plus the `idle` and `battery` config
sections. Every state is **gated on its assets** — a character only does what
its files allow, so behaviour grows as you add GIFs. (No GIFs ship yet; the
bundled characters use only static/blink/eyes/periodic-anim.)
