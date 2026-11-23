#!/usr/bin/env python3
"""Copy lib/mitlib.py into every skill folder that has a Python tool.

Each skill must work when copied on its own, so each carries its own
identical copy. Edit lib/mitlib.py, then run:  python3 tools/sync_lib.py
tests/test_repo.py fails if any copy drifts.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "lib", "mitlib.py")

for d in sorted(os.listdir(ROOT)):
    folder = os.path.join(ROOT, d)
    if d.startswith("mit-") and os.path.isfile(os.path.join(folder, "SKILL.md")):
        if any(f.endswith(".py") and f != "mitlib.py" for f in os.listdir(folder)):
            shutil.copyfile(SRC, os.path.join(folder, "mitlib.py"))
            print("synced", d)
