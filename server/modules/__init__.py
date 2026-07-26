"""Import every module file here so its @register decorator runs, without
anyone having to hand-maintain an import list. Adding a module is then just
"drop a new file in this folder" - see AGENTS.md hard rule 11.
"""
import importlib
import pkgutil

for _info in pkgutil.iter_modules(__path__):
    if _info.name != "base":
        importlib.import_module(f"{__name__}.{_info.name}")
