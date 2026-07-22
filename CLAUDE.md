# myCat — for contributors 🐱

Hi — and thank you for being here. myCat is a tiny desktop pet, and its little
characters (the "skins") are the whole point of it. This is a short, friendly
guide for anyone who'd like to add one or help out.

## 🎨 Make your own skin (step by step)

Good news: a skin is tiny. Under the hood it's just **one animated GIF inside a
`.zip`** — no JSON, no code, nothing to compile.

### 1. How a skin works

- The **ZIP's filename is the name shown in the menu** — `redcat.zip` appears as
  **redcat**.
- Inside the ZIP there's a single animated **`.gif`**.
- The GIF's **first frame is the resting pose** myCat shows while idle (for about
  5 seconds, or `--wait` seconds). Then the GIF plays through once and settles
  back on that first frame.
- Keep it within **300×500 px** — anything larger is scaled down automatically
  (the aspect ratio is preserved).
- Use a **transparent background**, so the cat sits on your desktop instead of
  inside a box.

### 2. Draw your frames

Draw your character as a few frames of animation — PNGs with a transparent
background work best. Frame 1 is the calm idle pose; the rest are the little
animation that plays now and then (a blink, a stretch, a wave… up to you).

### 3. Build the animated GIF

Any tool that exports an animated GIF works — GIMP, Aseprite, [ezgif.com](https://ezgif.com),
or ImageMagick from the terminal:

```bash
# From separate frames (frame1 = the idle pose):
convert -delay 12 -loop 0 frame1.png frame2.png frame3.png redcat.gif

# …or from a 2-frame sprite sheet (left half = idle, right half = action):
convert sheet.png -crop 50%x100% +repage -set delay '200,100' -loop 0 redcat.gif
```

`-delay` is in hundredths of a second per frame; `-loop 0` is fine — myCat
handles the "play once, then rest" behaviour itself.

### 4. Package it as a ZIP

The zip's name becomes the menu name, so name it nicely:

```bash
zip redcat.zip redcat.gif
```

### 5. Try it right away

- **Launch with it:** `mycat --image /path/to/redcat.zip`
- **Install it for keeps:** drop `redcat.zip` into your personal chars folder and
  it shows up in the right-click **Chars** menu instantly — no restart:
  - **Linux:** `~/.local/share/mycat/chars/` (or `$XDG_DATA_HOME/mycat/chars/`)
  - **macOS:** `~/Library/Application Support/mycat/chars/`
  - **Windows:** `%LOCALAPPDATA%\mycat\chars\`

### 6. Share it with everyone (optional)

Want it bundled with myCat for everyone? Put `redcat.zip` into `mycat/chars/`
and open a pull request. ⚠️ Please only share art **you drew yourself** — see
**Artwork & licensing** below.

### If something looks off

- **A black box around the cat** → the GIF needs a transparent background. (On
  Linux/X11 a compositor helps; without one, myCat clips the window to the cat's
  outline.)
- **It doesn't move** → make sure it's a real multi-frame animated GIF, not a
  single still image.
- **It's huge** → that's fine, it gets scaled down to fit 300×500.

### ✅ Quick recap

1. Draw your frames — **first frame = idle pose**, transparent background, ≤300×500.
2. Export them as one **animated GIF**.
3. `zip myname.zip myname.gif` — the **zip name is the menu name**.
4. Test it: `mycat --image myname.zip`, or drop the zip in your chars folder.
5. To contribute it: put it in `mycat/chars/` and open a PR — **only your own art.**

## 🐞 Hit a problem? Open an Issue

If something doesn't work, or you have an idea, please open an [Issue](../../issues).
Tell me what happened and how you ran it (your OS, the command) so I can reproduce
it.

## 🔀 Opening a pull request

When you open a PR, please add a short note about **what it does and why** — even a
sentence or two. It lets me understand and review it quickly. 🙏

## 💛 About artwork & licensing

I'm genuinely happy every single time someone shares an animation — thank you. I'll
be honest with you: I can't draw, and that's my biggest limitation here.

Because of licensing and repository size, **I can only accept artwork that you drew
yourself.** If a character wasn't made by you personally, I won't be able to merge
it — not because it isn't lovely, but because I can't take on art I don't have the
rights to. I hope you understand. 🙏

## 🌱 A little dream

One day I'd love to build a small site — a place to upload and download characters
and share them freely, without crowding the repo. If that idea excites you, I'd be
glad for the company.

Thank you, really. 🐾
