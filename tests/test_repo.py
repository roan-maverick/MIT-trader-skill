"""The repo itself: skill folders, frontmatter, the shared library copies, safety text, docs."""

import json
import os
import re
import unittest

from _load import ROOT

SKILLS = ["mit-scanner", "mit-regression", "mit-volatility", "mit-montecarlo", "mit-factors",
          "mit-portfolio", "mit-var", "mit-risk", "mit-broker", "mit-pairs", "mit-options",
          "mit-execution", "mit-autopilot", "mit-professor"]
# skills on the way to an order say plainly that nothing goes through without the user's yes
ORDER_PATH = ["mit-scanner", "mit-regression", "mit-volatility", "mit-montecarlo", "mit-portfolio",
              "mit-risk", "mit-broker", "mit-pairs", "mit-autopilot"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


class Repo(unittest.TestCase):
    def test_fourteen_skill_folders(self):
        found = sorted(d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_frontmatter(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertIn("description:", fm, s)
            desc = " ".join(fm.split("description:", 1)[1].split("argument-hint")[0].split())
            self.assertLess(len(desc), 1024, s)
            self.assertIn("Use when", desc, s)
            self.assertIn("## Safety", text, s)

    def test_order_path_safety(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertTrue("places an order" in text or "place an order" in text or "places, changes" in text, s)
            self.assertIn("yes", text, s)

    def test_every_tool_has_an_identical_mitlib(self):
        with open(os.path.join(ROOT, "lib", "mitlib.py"), encoding="utf-8") as fh:
            src = fh.read()
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            tools = [f for f in os.listdir(folder) if f.endswith(".py") and f != "mitlib.py"]
            if not tools:
                continue
            with open(os.path.join(folder, "mitlib.py"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), src, "%s/mitlib.py differs: run tools/sync_lib.py" % s)

    def test_skill_md_commands_exist(self):
        for s in SKILLS:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            for script in re.findall(r'\$\{CLAUDE_SKILL_DIR\}/([\w.]+\.py)', text):
                self.assertTrue(os.path.isfile(os.path.join(ROOT, s, script)), "%s: %s" % (s, script))

    def test_professor_has_26_lectures(self):
        files = sorted(os.listdir(os.path.join(ROOT, "mit-professor", "lectures")))
        self.assertEqual(files, ["L%02d.md" % i for i in range(1, 27)])

    def test_readme_names_every_skill_and_the_disclaimer(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)
        self.assertIn("Not affiliated with", readme)
        self.assertIn("Not financial advice", readme)
        self.assertIn("never without your yes", readme)

    def test_plugin_manifests(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            p = json.load(fh)
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            m = json.load(fh)
        self.assertEqual(p["name"], "mit-trader-skill")
        self.assertEqual(m["plugins"][0]["name"], p["name"])
        self.assertEqual(p["skills"], "./")

    def test_config_example_is_safe(self):
        with open(os.path.join(ROOT, "mit-portfolio", "config.example.json")) as fh:
            c = json.load(fh)
        self.assertTrue(c["paper"])
        self.assertFalse(c["allow_short"])
        self.assertFalse(c["allow_margin"])
        self.assertFalse(c["allow_options"])
        self.assertTrue(c["require_stop"])

    def test_no_secrets(self):
        pat = re.compile(r"(PK[A-Z0-9]{16,}|sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})")
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "fixtures")]
            for f in files:
                if f.endswith((".py", ".md", ".json")):
                    with open(os.path.join(base, f), encoding="utf-8") as fh:
                        self.assertIsNone(pat.search(fh.read()), f)


if __name__ == "__main__":
    unittest.main()
