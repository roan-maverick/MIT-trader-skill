# Reviewed for local use
"""The repo itself: one skill, its frontmatter, its guides, its safety text, the docs."""

import json
import os
import re
import unittest

from _load import ROOT

SKILL = os.path.join(ROOT, "mit-trader")
TOOLS = ["autopilot", "check", "execution", "factors", "hunt", "mitlib", "montecarlo", "options", "pairs",
         "portfolio", "scan", "signal", "ticket", "var", "vol"]
GUIDES = ["autopilot", "broker", "execution", "factors", "hunt", "montecarlo", "options", "pairs", "portfolio",
          "professor", "risk", "scanner", "signal-lab", "var", "volatility"]
OLD = r"/mit-(scanner|regression|volatility|montecarlo|factors|portfolio|var|risk|broker|pairs|options|execution|autopilot|professor)\b"


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as fh:
        return fh.read()


class Repo(unittest.TestCase):
    def test_exactly_one_skill(self):
        found = [d for d in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, d, "SKILL.md"))]
        self.assertEqual(found, ["mit-trader"])

    def test_frontmatter(self):
        text = read(SKILL, "SKILL.md")
        fm = re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1)
        self.assertIn("name: mit-trader\n", fm + "\n")
        desc = " ".join(fm.split("description:", 1)[1].split("argument-hint")[0].replace(">-", "").split())
        self.assertLess(len(desc), 1024)
        self.assertIn("Use for", desc)
        self.assertIn("never without your yes", desc)

    def test_tools_and_guides(self):
        self.assertEqual(sorted(f[:-3] for f in os.listdir(os.path.join(SKILL, "scripts")) if f.endswith(".py")), TOOLS)
        self.assertEqual(sorted(f[:-3] for f in os.listdir(os.path.join(SKILL, "references")) if f.endswith(".md")), GUIDES)
        files = sorted(f for f in os.listdir(os.path.join(SKILL, "references", "lectures")) if re.match(r"L\d\d\.md$", f))
        self.assertEqual(files, ["L%02d.md" % i for i in range(1, 27)])

    def test_every_command_and_guide_named_exists(self):
        lectures = [os.path.join("references", "lectures", "L%02d.md" % i) for i in range(1, 27)]
        for name in ["SKILL.md"] + [os.path.join("references", g + ".md") for g in GUIDES] + lectures:
            text = read(SKILL, name)
            for script in re.findall(r"scripts/(\w+\.py)", text):
                self.assertTrue(os.path.isfile(os.path.join(SKILL, "scripts", script)), "%s: %s" % (name, script))
            for ref in re.findall(r"references/([\w-]+\.md)", text):
                self.assertTrue(os.path.isfile(os.path.join(SKILL, "references", ref)), "%s: %s" % (name, ref))
            self.assertIsNone(re.search(OLD, text), name)

    def test_no_old_skill_names_in_tools_or_readme(self):
        for f in TOOLS:
            self.assertIsNone(re.search(OLD, read(SKILL, "scripts", f + ".py")), f)
        self.assertIsNone(re.search(OLD, read(ROOT, "README.md")))

    def test_safety_everywhere(self):
        self.assertIn("never batch yeses", read(SKILL, "SKILL.md").lower())
        for g in GUIDES:
            self.assertIn("## Safety", read(SKILL, "references", g + ".md"), g)

    def test_readme(self):
        readme = read(ROOT, "README.md")
        for phrase in ("one Claude skill", "overnight", "Not affiliated with", "Not financial advice",
                       "never without your yes", "hunt"):
            self.assertIn(phrase, readme)

    def test_plugin_manifests(self):
        p = json.loads(read(ROOT, ".claude-plugin", "plugin.json"))
        m = json.loads(read(ROOT, ".claude-plugin", "marketplace.json"))
        self.assertEqual(p["name"], "mit-trader-skill")
        self.assertEqual(m["plugins"][0]["name"], p["name"])

    def test_config_example_is_safe(self):
        c = json.loads(read(SKILL, "config.example.json"))
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
                    self.assertIsNone(pat.search(read(base, f)), f)


if __name__ == "__main__":
    unittest.main()
