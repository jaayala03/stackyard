"""Desktop notifications (libnotify) for actions that finish while the user
is looking elsewhere."""

import gi

try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
except (ValueError, ImportError):
    Notify = None

from .i18n import _

MODES = [("background", "When the window is not in focus"), ("always", "Always"), ("never", "Never")]

_ready = False
_live = []  # keep references so action callbacks are not garbage-collected


def available():
    global _ready
    if Notify is None:
        return False
    if not _ready:
        _ready = Notify.init("Panel DDEV")
    return _ready


def should_notify(mode, window):
    if mode == "never":
        return False
    if mode == "always":
        return True
    return not (window.get_visible() and window.is_active())


def finished(title, ok, icon, on_click=None):
    if not available():
        return
    body = _("Finished successfully.") if ok else _("Something went wrong. Open Panel DDEV to see the output.")
    n = Notify.Notification.new(("✔ " if ok else "✘ ") + title, body, icon)
    n.set_urgency(Notify.Urgency.NORMAL if ok else Notify.Urgency.CRITICAL)
    if on_click:
        try:
            n.add_action("default", _("Open"), lambda *_a: on_click())
        except TypeError:
            pass  # some servers do not support actions
    _live.append(n)
    del _live[:-10]
    try:
        n.show()
    except Exception:  # noqa: BLE001 - no notification daemon running
        pass
