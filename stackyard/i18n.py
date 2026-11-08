"""Minimal translation layer.

UI strings are written in English in the code and wrapped with ``_()``.
Translations live in ``TRANSLATIONS`` keyed by the English text. Placeholders
use ``str.format`` syntax, e.g. ``_("Cloning {repo}").format(repo=url)``.
"""

import locale
import os

from .locale_es import ES

SUPPORTED = ("en", "es")
TRANSLATIONS = {"es": ES}

_current = "en"


def system_language():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            code = value.split(":")[0][:2].lower()
            return code if code in SUPPORTED else "en"
    try:
        code = (locale.getlocale()[0] or "en")[:2].lower()
    except ValueError:
        code = "en"
    return code if code in SUPPORTED else "en"


def set_language(lang):
    """lang: 'auto', 'en' or 'es'."""
    global _current
    _current = system_language() if lang in (None, "", "auto") else lang
    if _current not in SUPPORTED:
        _current = "en"


def current_language():
    return _current


def _(text):
    return TRANSLATIONS.get(_current, {}).get(text, text)
