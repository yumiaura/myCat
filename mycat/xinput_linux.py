"""Pure-Python global key/click COUNTER for Linux/X11 via python-xlib (XRecord).

This is the Linux counting backend so `pip install mycat` works out of the box:
pynput would need the `evdev` C extension (no wheels, needs a compiler), while
`python-xlib` is pure Python with wheels. Like the pynput path, only integers
survive — the key identity is dropped inside the callback and never stored.

Unavailable (returns False from `start()`) off X11 (e.g. Wayland) or if the X
server lacks the RECORD extension; the diary then keeps only the cursor path.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


def available() -> bool:
    """True if an X11 display with the RECORD extension is reachable."""
    try:
        import Xlib.display

        display = Xlib.display.Display()
        try:
            return bool(display.has_extension("RECORD"))
        finally:
            display.close()
    except Exception as exc:  # no DISPLAY, Wayland, missing lib…
        logger.debug("X RECORD unavailable: %s", exc)
        return False


class InputCounter:
    """Count key presses and mouse-button presses globally via X RECORD.

    `on_key` / `on_click` are called (no arguments) once per event; keep them
    cheap and thread-safe — they run on the record thread.
    """

    def __init__(
        self,
        on_key: Callable[[], None] | None = None,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        self.on_key = on_key
        self.on_click = on_click
        self.thread: threading.Thread | None = None
        self.control_display = None
        self.record_display = None
        self.context = None

    @property
    def active(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self) -> bool:
        """Begin counting. Returns True on success, False if X RECORD is unusable."""
        if self.active:
            return True
        try:
            import Xlib.display
            from Xlib import X
            from Xlib.ext import record
        except Exception as exc:
            logger.debug("python-xlib unavailable: %s", exc)
            return False
        try:
            self.control_display = Xlib.display.Display()
            self.record_display = Xlib.display.Display()
            if not self.record_display.has_extension("RECORD"):
                logger.warning("X server has no RECORD extension — key/click counting off")
                self.close()
                return False
            self.context = self.record_display.record_create_context(
                0,
                [record.AllClients],
                [
                    {
                        "core_requests": (0, 0),
                        "core_replies": (0, 0),
                        "ext_requests": (0, 0, 0, 0),
                        "ext_replies": (0, 0, 0, 0),
                        "delivered_events": (0, 0),
                        "device_events": (X.KeyPress, X.ButtonPress),
                        "errors": (0, 0),
                        "client_started": False,
                        "client_died": False,
                    }
                ],
            )
        except Exception:
            logger.exception("Failed to set up X RECORD context")
            self.close()
            return False

        self.thread = threading.Thread(target=self.run, name="mycat-xinput", daemon=True)
        self.thread.start()
        return True

    def run(self) -> None:
        from Xlib import X
        from Xlib.ext import record
        from Xlib.protocol import rq

        def handler(reply) -> None:
            if reply.category != record.FromServer or reply.client_swapped:
                return
            if not reply.data or reply.data[0] < 2:  # not a device event
                return
            data = reply.data
            while data:
                event, data = rq.EventField(None).parse_binary_value(
                    data, self.record_display.display, None, None
                )
                if event.type == X.KeyPress:
                    if self.on_key is not None:
                        self.on_key()
                elif event.type == X.ButtonPress:
                    if self.on_click is not None:
                        self.on_click()

        try:
            self.record_display.record_enable_context(self.context, handler)
        except Exception:
            logger.debug("X RECORD loop ended")
        finally:
            try:
                self.record_display.record_free_context(self.context)
            except Exception:
                pass

    def stop(self) -> None:
        try:
            if self.context is not None and self.control_display is not None:
                self.control_display.record_disable_context(self.context)
                self.control_display.flush()
        except Exception:
            pass
        thread = self.thread
        if thread is not None:
            thread.join(timeout=2)
        self.close()

    def close(self) -> None:
        for display in (self.record_display, self.control_display):
            try:
                if display is not None:
                    display.close()
            except Exception:
                pass
        self.record_display = None
        self.control_display = None
        self.context = None
        self.thread = None


__all__ = ["available", "InputCounter"]
