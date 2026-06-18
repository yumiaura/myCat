# Live-cat demo (local prototype)

A throwaway prototype of roadmap vertical **B — "the cat feels alive"**. It is
**not** wired into the app and is meant to be run directly so we can *see* the
idea before committing to a design.

```bash
python demo/live_cat_demo.py
```

It reuses the real mycat window and layers liveliness on top:

- **Ambient motion** — the cat moves on its own at a varied cadence instead of
  sitting still after the first play.
- **CPU-reactive energy** — a busier machine makes a busier cat; the cadence
  scales with whole-system CPU read natively from `/proc/stat` (no deps).
- **Reacts to you** — click or grab the cat and it perks up immediately.
- **Naps** — after ~30 s with no interaction (and low CPU) it settles into a
  slow, rare cadence; activity or load wakes it back up.

A small pill above the cat narrates the current mood and CPU, and the same
transitions are logged to the console (`[live-cat] mood -> …`).

### Try it
- Leave it alone for ~30 s → it goes `napping`.
- Run a CPU load (e.g. `yes > /dev/null` on a couple of cores) → it turns
  `lively` and moves more often.
- Click/grab the cat → instant `excited` reaction.

### Notes / not done
- No new art: liveliness is expressed by *how often* the existing GIF plays, not
  by new poses. Mood-specific sprites (sleep, eating-while-charging) are future
  work.
- Battery/charging ("the cat eats while charging") isn't shown — this dev box has
  no battery. That part of vertical B needs an eating sprite anyway.
