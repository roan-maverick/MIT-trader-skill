"""The worked example, end to end on real data: NVDA after its November 2026 selloff.

Every number in README.md's walkthrough is checked here, offline, from the
fixtures in tests/fixtures/bars (daily closes to Friday 2026-11-20).
"""

import json
import os
import unittest

from _load import ASOF, BARS, Workdir, load, run

scan = load("scan")
signal = load("signal")
vol = load("vol")
mc = load("montecarlo")
factors = load("factors")
port = load("portfolio")
var = load("var")
risk = load("check")
broker = load("ticket")
D = ["--data", BARS, "--asof", ASOF]


def read(wd, *p):
    with open(os.path.join(wd, *p)) as fh:
        return json.load(fh)


def write(p, obj):
    with open(p, "w") as fh:
        json.dump(obj, fh)


class NvdaWalkthrough(unittest.TestCase):
    def test_the_whole_reel(self):
        with Workdir() as wd:
            # 1. scanner
            code, out = run(scan, "run", "--write", *D)
            cand = read(wd, "candidates.json")
            self.assertEqual(cand["scanned"], 42)
            self.assertEqual(cand["n_tests"], 168)
            self.assertEqual(len(cand["candidates"]), 32)
            nv = [c for c in cand["candidates"] if c["symbol"] == "NVDA"][0]
            self.assertEqual(nv["setup"], "dip")
            self.assertAlmostEqual(nv["z20"], -2.29, places=2)
            self.assertAlmostEqual(nv["ret_21d"], -0.408, delta=0.001)
            self.assertIn("NVDA     dip    close 125.53", out)
            # 2. signal lab
            code, out = run(signal, "test", "NVDA", "--setup", "dip", "--n-tests", "168", "--write", *D)
            s = read(wd, "signals.json")["results"]["NVDA:dip"]
            self.assertEqual(s["events"]["count"], 26)
            self.assertAlmostEqual(s["events"]["hit_rate"], 0.69, places=2)
            self.assertAlmostEqual(s["events"]["t_excess"], 0.79, places=2)
            self.assertAlmostEqual(s["t_bar"], 3.62, places=2)
            self.assertEqual(s["verdict"], "NONE")
            # 3. volatility plan
            code, out = run(vol, "plan", "NVDA", "--setup", "dip", "--write", "--replace", *D)
            p = read(wd, "plan.json")["plans"][0]
            self.assertEqual((p["entry"], p["stop"], p["target"]), (125.53, 109.43, 165.18))
            self.assertAlmostEqual(p["vol_horizon"], 0.1372, places=4)
            # 4. Monte Carlo (seed 18)
            code, out = run(mc, "run", "--write", *D)
            m = read(wd, "plan.json")["plans"][0]
            self.assertAlmostEqual(m["montecarlo"]["p_target"], 0.038, places=3)
            self.assertAlmostEqual(m["montecarlo"]["p_stop"], 0.285, places=3)
            self.assertEqual(m["montecarlo"]["kelly_continuous"], 0.0)
            self.assertEqual((m["history"]["fired"], m["history"]["target"], m["history"]["stop"]), (26, 2, 5))
            self.assertIn("close to a coin flip", out)
            # 5. Kelly says no; fixed sizing gives 6 shares
            code, out = run(port, "size", "--write")
            self.assertEqual(read(wd, "orders.json")["orders"], [])
            self.assertIn("Kelly says do not bet", out)
            code, out = run(port, "size", "--method", "fixed", "--write")
            o = read(wd, "orders.json")["orders"][0]
            self.assertEqual((o["symbol"], o["qty"], o["stop_loss_stop_price"], o["take_profit_limit_price"]),
                             ("NVDA", "6", "109.43", "165.18"))
            # 6. VaR
            code, out = run(var, "run", "--include-orders", "--write", *D)
            v = read(wd, "var.json")
            self.assertAlmostEqual(v["var_hist"], 58.85, places=2)
            self.assertEqual(v["kupiec"]["exceptions"], 2)
            # 7. risk: pass at 10:00 Monday, blocked at 9:40, on Sunday, and with 7 shares
            code, out = run(risk, "--now", "2026-11-23 10:00")
            self.assertEqual(code, 0)
            self.assertIn("max loss $96.60", out)
            self.assertIn("rated this setup NONE", out)
            code, out = run(risk, "--now", "2026-11-23 09:40", "--no-write")
            self.assertIn("before 09:45", out)
            code, out = run(risk, "--now", "2026-11-22 10:00", "--no-write")
            self.assertIn("closed (weekend)", out)
            seven = dict(read(wd, "orders.json"))
            seven["orders"] = [dict(seven["orders"][0], qty="7")]
            path7 = os.path.join(wd, "o7.json")
            write(path7, seven)
            code, out = run(risk, "--now", "2026-11-23 10:00", "--orders", path7, "--no-write")
            self.assertEqual(code, 1)
            self.assertIn("$112.70 at the stop", out)
            # 8. broker: three gates
            code, out = run(broker, "--now", "2026-11-23 10:01", "show")
            self.assertIn("#1 READY  (PAPER account)", out)
            self.assertIn('"stop_loss_stop_price": "109.43"', out)
            for reply in ("sure", "yes buy 6 TSLA", "yes to all", "yes buy 7"):
                code, out = run(broker, "--now", "2026-11-23 10:02", "approve", "--index", "1", "--reply", reply)
                self.assertEqual(code, 1, reply)
                self.assertIn("Not recorded", out)
            code, out = run(broker, "--now", "2026-11-23 10:02", "approve", "--index", "1", "--reply", "yes, buy 6 NVDA")
            self.assertEqual(code, 0)
            self.assertIn("place_stock_order", out)
            code, out = run(broker, "--now", "2026-11-23 10:03", "result", "--index", "1", "--status", "placed",
                            "--broker-id", "paper-1", "--filled-qty", "6", "--filled-price", "125.60")
            pf = read(wd, "portfolio.json")
            self.assertEqual(pf["positions"][0]["qty"], 6.0)
            self.assertEqual(pf["positions"][0]["plan"]["stop"], 109.43)
            code, out = run(risk, "--now", "2026-11-23 10:10", "--no-write")
            self.assertIn("duplicate", out)

    def test_an_edited_order_is_not_ready(self):
        with Workdir() as wd:
            run(vol, "plan", "NVDA", "--write", "--replace", *D)
            run(port, "size", "--method", "fixed", "--write")
            run(risk, "--now", "2026-11-23 10:00")
            doc = read(wd, "orders.json")
            doc["orders"][0]["qty"] = "5"
            write(os.path.join(wd, "orders.json"), doc)
            code, out = run(broker, "--now", "2026-11-23 10:01", "show")
            self.assertIn("changed after the risk gate", out)
            code, out = run(broker, "--now", "2026-11-24 10:01", "show")
            self.assertIn("NOT READY", out)

    def test_factors(self):
        r = factors.beta("NVDA", "SPY", BARS, ASOF)
        self.assertAlmostEqual(r["beta"], 1.93, places=2)
        self.assertLess(abs(r["alpha_t"]), 2)
        p = factors.pca(["SPY", "QQQ", "TLT", "GLD", "NVDA", "JPM", "XLE", "PG"], BARS, ASOF)
        self.assertEqual(len(p["components"]), 3)
        self.assertGreater(p["components"][0]["share_of_variance"], p["components"][1]["share_of_variance"])


if __name__ == "__main__":
    unittest.main()
