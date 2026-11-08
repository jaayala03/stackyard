"""Fails if a string passed to _() has no Spanish translation (or a placeholder mismatch)."""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from panel_ddev import ddev, git, notify, settings  # noqa: E402
from panel_ddev.app import STATUS_LABELS  # noqa: E402
from panel_ddev.dialogs import ProjectDialog  # noqa: E402
from panel_ddev.locale_es import ES  # noqa: E402

found = set()
for f in (ROOT / "panel_ddev").glob("*.py"):
    for n in ast.walk(ast.parse(f.read_text())):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
                and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
            found.add(n.args[0].value)
# strings translated indirectly through constants
found |= {"Generic (no PHP)", ddev.AUTO_TYPE[1]}  # the other type labels are brand names
found |= set(STATUS_LABELS.values()) | {d for _l, d, _c in git.STATUS_INFO.values()}
found |= {label for _v, label in settings.THEMES} | {"System default"} | {label for _v, label in notify.MODES}
found |= set(ProjectDialog.TITLES.values()) | set(ProjectDialog.OK.values())

missing = sorted(s for s in found if s not in ES)
placeholders = sorted(s for s in found if s in ES and set(re.findall(r"{\w+}", s)) != set(re.findall(r"{\w+}", ES[s])))
for s in missing:
    print("missing:", repr(s))
for s in placeholders:
    print("placeholder mismatch:", repr(s))
print(f"{len(found)} strings, {len(missing)} missing, {len(placeholders)} mismatched")
sys.exit(1 if missing or placeholders else 0)
