# Live-cat demo (local prototype)

Prototype of roadmap vertical **B — "the cat feels alive"**, phase 1. It makes
the cat lively by **animating the existing sprite with code** — no new art, and
**no numbers on screen**: system load is shown as the cat's *mood*, not a percent.

Run it directly (not wired into the app, not pushed):

```bash
python demo/live_cat_demo.py
python demo/live_cat_demo.py --mood stress   # force one mood, for screenshots
```

## Moods (all procedural transforms of one sprite)

| Mood | Look | Trigger |
|---|---|---|
| `sleep` | slow breathing, dimmed, rising `z z Z` | idle a while + calm box |
| `yawn` | a vertical stretch | wake/sleep transition |
| `idle` | gentle breathing | default |
| `play` | bouncy hops + squash | **click the cat** |
| `aggro` | short random shake | random (personality) |
| `stress` | constant jitter, puffed-up, red tint | the box is busy (high CPU) |

Load is read internally from `/proc/stat` (smoothed) and mapped onto a calm↔busy
axis — it is **never shown as a number**. Mood changes are logged to the console.

## How it renders
Each frame is drawn onto a fixed-size padded canvas with a **foot-anchored**
transform (squash/stretch grows from the feet) and fed to the real
`PixelCatWindow` via `current_pixmap`, so transparency, dragging and the
no-compositor shape-mask all keep working. The padding gives headroom so
stretch/jitter never gets clipped.

## Honest limits (→ phase 2, ComfyUI pipeline)
Transforms can only move the *one* pose. Genuinely different poses need real
sprites and are deferred to the generation pipeline:
- a curled-up **sleep** pose (here: same pose, dimmed + Zzz),
- real **fur-on-end** for stress (here: puff-scale + red tint),
- **presenting its back to be petted** (not faked at all yet),
- ear-flattening for `aggro`.

Battery / "eats while charging" isn't shown — this dev box has no battery and it
needs an eating sprite anyway.
