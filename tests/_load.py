"""Load a tool from a skill folder (the folder names have hyphens) and run it."""

import contextlib
import importlib.util
import io
import os
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
BARS = os.path.join(FIX, "bars")
ASOF = "2026-11-20"


def load(folder, name):
    path = os.path.join(ROOT, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("mit_%s_%s" % (folder.replace("-", "_"), name), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(mod, *argv):
    """Call a tool's main(argv); return (exit code, printed text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.main(list(argv))
    return code, buf.getvalue()


class Workdir(object):
    """A fresh mit/ folder for one test (MIT_DIR points at it)."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="mit-test-")
        self.old = os.environ.get("MIT_DIR")
        os.environ["MIT_DIR"] = self.dir
        return self.dir

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("MIT_DIR", None)
        else:
            os.environ["MIT_DIR"] = self.old
        shutil.rmtree(self.dir, ignore_errors=True)
