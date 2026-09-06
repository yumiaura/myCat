#!/usr/bin/env python3
"""Dev CLI to bake a VRM/glb into a myCat character zip.

Thin wrapper around :mod:`mycat.vrm_bake` (the same code the in-app *Import VRM…*
action uses). Rendering needs a real GL context; on a headless box run it under
``xvfb-run``:

    xvfb-run -a python3 tools/bake_vrm.py tools/vrm/N00.vrm

By default the baked zip lands in the per-user chars dir, so it shows up in the
right-click Chars menu immediately.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mycat.vrm_bake import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
