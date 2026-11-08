"""Share a project on the internet with `ddev share` (temporary public URL).

cloudflared quick tunnels need no account, so it is the preferred provider;
ngrok is used if it is the only one installed."""

import re
import shutil

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from . import ddev  # noqa: E402
from .i18n import _  # noqa: E402

URL_RE = re.compile(r"https://[A-Za-z0-9.-]+\.(?:trycloudflare\.com|ngrok(?:-free)?\.(?:app|dev|io)|ngrok\.io)\b")

# Official Cloudflare apt repository (https://pkg.cloudflare.com/)
INSTALL_CLOUDFLARED = (
    "sudo mkdir -p --mode=0755 /usr/share/keyrings && "
    "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && "
    "echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' "
    "| sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null && "
    "sudo apt-get update -qq && sudo apt-get install -y cloudflared"
)


def provider():
    if shutil.which("cloudflared"):
        return "cloudflared"
    if shutil.which("ngrok"):
        return "ngrok"
    return None


def share_command(prov):
    return f"ddev share --provider={prov}"


def install_script():
    return ddev.script_simple(None, [(_("Installing cloudflared"), INSTALL_CLOUDFLARED)], _("cloudflared installed"))


def find_url(text):
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


class ShareDialog(Gtk.Dialog):
    """Shows the public link once the tunnel is up."""

    def __init__(self, parent, project_name, url):
        super().__init__(title=_("{name} is shared").format(name=project_name), transient_for=parent, modal=False)
        self.set_default_size(460, -1)
        self.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        box = self.get_content_area()
        box.set_spacing(10)
        box.set_border_width(16)
        box.pack_start(Gtk.Label(label=_("Anyone with this link can see your site:"), xalign=0), False, False, 0)
        entry = Gtk.Entry(text=url, editable=False)
        box.pack_start(entry, False, False, 0)
        buttons = Gtk.Box(spacing=8)
        copy = Gtk.Button(label=_("Copy link"))
        copy.connect("clicked", lambda *_a: (Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(url, -1), copy.set_label(_("Copied ✔"))))
        open_btn = Gtk.Button(label=_("Open"))
        open_btn.connect("clicked", lambda *_a: Gtk.show_uri_on_window(self, url, Gdk.CURRENT_TIME))
        buttons.pack_start(copy, False, False, 0)
        buttons.pack_start(open_btn, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        note = Gtk.Label(label=_("The link works while the “share” tab is open. Close that tab to stop sharing."),
                         xalign=0, wrap=True, max_width_chars=52)
        note.get_style_context().add_class("dim-label")
        box.pack_start(note, False, False, 0)
        self.connect("response", lambda d, _r: d.destroy())
        self.show_all()
