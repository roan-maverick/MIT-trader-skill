# Reviewed for local use
"""The overnight research and the bot: the real-data result, and proof it finds a real edge."""

import json
import os
import unittest

from _load import UNIVERSE, Workdir, load, run
import _planted

hunt = load("hunt")
autopilot = load("autopilot")
broker = load("ticket")


def read(wd, *p):
    with open(os.path.join(wd, *p)) as fh:
        return json.load(fh)


class Library(unittest.TestCase):
    def test_51_variants(self):
        lib = hunt.library()
        self.assertEqual(len(lib), 51)
        self.assertEqual(len(set(v["id"] for v in lib)), 51)

    def test_rolling_trend_t_matches_ols(self):
        import math
        import random
        import mitlib as M
        rng = random.Random(4)
        lp = [0.0]
        for _ in range(200):
            lp.append(lp[-1] + 0.001 + rng.gauss(0, 0.01))
        fast = hunt.trend_t(lp, 63)
        for i in (62, 120, 200):
            slow = M.ols(lp[i - 62:i + 1], [float(k) for k in range(63)])["t"][1]
            self.assertAlmostEqual(fast[i], slow, places=6)

    def test_benjamini_hochberg(self):
        self.assertEqual(hunt.bh_select([0.001, 0.01, 0.03, 0.2, 0.9], 0.10), {0, 1, 2})
        self.assertEqual(hunt.bh_select([0.5, 0.6], 0.10), set())


class RealMarket(unittest.TestCase):
    """138 US stocks and ETFs plus Bitcoin, 10 years to 2026-11-20: nothing survives."""

    def test_research_approves_nothing_and_the_bot_stands_down(self):
        with Workdir() as wd:
            code, out = run(autopilot, "research", "--data", UNIVERSE, "--asof", "2026-11-20")
            doc = read(wd, "strategies.json")
            self.assertEqual(len(doc["symbols"]), 138)
            self.assertEqual(doc["variants"], 51)
            self.assertEqual(doc["history"]["split"], "2024-05-08")
            self.assertEqual(doc["approved"], [])
            top = doc["results"][0]
            self.assertEqual(top["id"], "dip-w20-zm1.5-h5")
            self.assertAlmostEqual(top["excess_in"], 0.0035, delta=0.00005)
            self.assertAlmostEqual(top["t_in"], 2.15, places=2)
            self.assertAlmostEqual(top["excess_out"], 0.0, delta=0.0001)
            self.assertIn("the bot stands down", out)
            code, out = run(autopilot, "run", "--data", UNIVERSE, "--asof", "2026-11-20", "--now", "2026-11-23 10:00")
            self.assertIn("approved 0 rule(s)", out)
            self.assertIn("Nothing to approve", out)


class PlantedEdge(unittest.TestCase):
    """A market where dips really do bounce: the hunt must find it and the bot must trade it."""

    def test_finds_the_edge_and_makes_tickets(self):
        with Workdir() as wd:
            data = os.path.join(wd, "planted.json")
            last = _planted.make(data)
            self.assertEqual(last, "2026-08-31")
            run(autopilot, "research", "--data", data)
            doc = read(wd, "strategies.json")
            self.assertIn("dip-w10-zm2.0-h5", doc["approved"])
            best = [r for r in doc["results"] if r["id"] == "dip-w10-zm2.0-h5"][0]
            self.assertGreater(best["t_in"], 10)
            self.assertGreater(best["t_out"], 5)
            for r in doc["results"]:
                if r["family"] in ("trend", "breakout", "calm"):
                    self.assertNotEqual(r["status"], "APPROVED", r["id"])  # no edge planted there
            code, out = run(autopilot, "run", "--data", data, "--now", "2026-09-03 10:00")
            self.assertIn("Bot mode", out)
            self.assertIn("Passed the risk gate: 3", out)
            plans = read(wd, "plan.json")["plans"]
            self.assertTrue(all(p.get("strategy") for p in plans))
            self.assertTrue(all("overnight research" in p["montecarlo"]["drift_source"] for p in plans))
            orders = read(wd, "orders.json")["orders"]
            self.assertTrue(all(o["plan"]["strategy"] for o in orders))
            code, out = run(broker, "--now", "2026-09-03 10:05", "show")
            self.assertEqual(out.count("READY  (PAPER account)"), 3)
            risk = read(wd, "state", "risk.json")["verdicts"]
            self.assertFalse(any("no proven edge" in w for v in risk for w in v["warnings"]))


if __name__ == "__main__":
    unittest.main()
