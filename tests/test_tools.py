# Reviewed for local use
"""Pairs, options, execution, autopilot, crypto and the risk gate's edge cases."""

import json
import os
import unittest

from _load import ASOF, BARS, ROOT, Workdir, load, run

pairs = load("pairs")
options = load("options")
execution = load("execution")
autopilot = load("autopilot")
risk = load("check")
port = load("portfolio")
mc = load("montecarlo")
vol = load("vol")
signal = load("signal")
D = ["--data", BARS, "--asof", ASOF]


def read(wd, *p):
    with open(os.path.join(wd, *p)) as fh:
        return json.load(fh)


def write(p, obj):
    with open(p, "w") as fh:
        json.dump(obj, fh)


class Pairs(unittest.TestCase):
    def test_scan_is_honest_about_luck(self):
        code, out = run(pairs, "scan", *D)
        self.assertIn("Tested 56 pairs", out)
        self.assertIn("Cointegrated at 5%: 2. By luck alone about 3 would pass.", out)

    def test_gld_gdx_not_cointegrated(self):
        r = pairs.test("GLD", "GDX", BARS, ASOF)
        self.assertIsNone(r["cointegrated_at"])

    def test_pair_plan_needs_a_short(self):
        with Workdir() as wd:
            run(pairs, "plan", "LRCX", "KLAC", "--write", *D)
            run(mc, "run", "--write", *D)
            p = read(wd, "plan.json")["plans"][0]
            self.assertEqual(p["montecarlo"]["model"], "ou")
            run(port, "size", "--method", "fixed", "--write")
            orders = read(wd, "orders.json")["orders"]
            self.assertEqual([o["side"] for o in orders], ["buy", "sell"])
            code, out = run(risk, "--now", "2026-11-23 11:00", "--no-write")
            self.assertIn("short: selling", out)
            self.assertEqual(code, 1)


class Options(unittest.TestCase):
    def test_price_and_iv(self):
        code, out = run(options, "price", "--spot", "42", "--strike", "40", "--days", "182.5", "--vol", "0.2", "--rate", "0.1", "--json")
        self.assertAlmostEqual(json.loads(out)["price"], 4.7594, places=3)
        code, out = run(options, "iv", "--price", "4.7594", "--spot", "42", "--strike", "40", "--days", "182.5", "--rate", "0.1", "--json")
        self.assertAlmostEqual(json.loads(out)["implied_vol"], 0.2, places=3)

    def test_breeden_litzenberger_recovers_lognormal(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "mit-trader", "scripts"))
        import mitlib as M
        with Workdir() as wd:
            f = os.path.join(wd, "chain.csv")
            with open(f, "w") as fh:
                fh.write("strike,call\n")
                for k in range(40, 261, 2):
                    fh.write("%d,%.6f\n" % (k, M.bs(125.53, k, 30 / 365.0, 0.04, 0.6)["price"]))
            code, out = run(options, "chain", "--file", f, "--spot", "125.53", "--days", "30", "--json")
            d = json.loads(out)
            self.assertAlmostEqual(d["mass_captured"], 1.0, delta=0.01)
            for k, p in d["prob_above"]:
                if 100 <= k <= 160:
                    ln = M.norm_cdf(M.bs(125.53, k, 30 / 365.0, 0.04, 0.6)["d2"])
                    self.assertAlmostEqual(p, ln, delta=0.01)

    def test_straddle_move(self):
        code, out = run(options, "move", "--spot", "100", "--call", "4", "--put", "4", "--json")
        d = json.loads(out)
        self.assertAlmostEqual(d["one_sd_move"], 8 / 0.7978845608, places=3)


class Execution(unittest.TestCase):
    def test_small_order_is_one_order(self):
        p = execution.plan("NVDA", 6, adv=250000000, data_dir=BARS, asof=ASOF)
        self.assertTrue(p["one_order"])

    def test_urgency_front_loads(self):
        even = execution.plan("NVDA", 5000000, adv=250000000, urgency=0, slices=6, data_dir=BARS, asof=ASOF)
        fast = execution.plan("NVDA", 5000000, adv=250000000, urgency=3, slices=6, data_dir=BARS, asof=ASOF)
        self.assertEqual(len(set(s["qty"] for s in even["schedule"][:-1])), 1)
        self.assertGreater(fast["schedule"][0]["qty"], 2 * even["schedule"][0]["qty"])
        self.assertEqual(sum(s["qty"] for s in fast["schedule"]), 5000000)
        self.assertLess(fast["cost_sd_usd"], even["cost_sd_usd"])


class Autopilot(unittest.TestCase):
    def test_run_writes_a_report_and_places_nothing(self):
        with Workdir() as wd:
            code, out = run(autopilot, "run", "--now", "2026-11-23 10:00", *D)
            self.assertIn("Setups found: 32. Proven edge (the signal lab EDGE): 0.", out)
            self.assertIn("Nothing was ordered", out)
            self.assertTrue(os.path.exists(os.path.join(wd, "report.md")))
            self.assertFalse(os.path.exists(os.path.join(wd, "state", "broker.json")))
            sizes = {o["symbol"] for o in read(wd, "orders.json")["orders"]}
            self.assertNotIn("GDX", sizes)  # Kelly zero: no measured edge

    def test_watch_closes_crypto_at_its_stop(self):
        with Workdir() as wd:
            write(os.path.join(wd, "portfolio.json"), {"cash": 9000, "positions": [{"symbol": "BTC-USD", "qty": 0.01, "price": 60000,
                  "plan": {"stop": 59000, "target": 70000, "setup": "dip", "horizon_days": 5, "asof": "2026-11-19"}}]})
            code, out = run(autopilot, "watch", "--now", "2026-11-22 03:00", *D)
            self.assertIn("STOP reached", out)
            o = read(wd, "orders.json")["orders"][0]
            self.assertEqual((o["symbol"], o["side"], o["qty"]), ("BTC/USD", "sell", "0.01"))
            code, out = run(risk, "--now", "2026-11-22 03:05", "--no-write")
            self.assertIn("PASS", out)  # an exit, on a Sunday night: crypto never waits for the bell
            self.assertIn("exit", out)


class RiskEdges(unittest.TestCase):
    def setUp(self):
        self.base = {"id": "o1", "symbol": "NVDA", "asset_class": "us_equity", "side": "buy", "qty": "6",
                     "type": "market", "time_in_force": "gtc", "order_class": "bracket",
                     "take_profit_limit_price": "165.18", "stop_loss_stop_price": "109.43",
                     "plan": {"entry": 125.53, "stop": 109.43, "target": 165.18, "setup": "dip"}}

    def check(self, wd, order, now="2026-11-23 10:00", cfg=None):
        if cfg:
            write(os.path.join(wd, "config.json"), cfg)
        write(os.path.join(wd, "orders.json"), {"orders": [order]})
        return run(risk, "--now", now, "--no-write")

    def test_holiday_wrong_side_stop_options_require_edge(self):
        with Workdir() as wd:
            code, out = self.check(wd, self.base, "2026-11-26 11:00")
            self.assertIn("NYSE holiday", out)
            bad = dict(self.base, stop_loss_stop_price="130.00")
            code, out = self.check(wd, bad)
            self.assertIn("wrong side", out)
            opt = dict(self.base, symbol="NVDA261218C00130000")
            code, out = self.check(wd, opt)
            self.assertIn("options are off", out)
            write(os.path.join(wd, "signals.json"), {"results": {"NVDA:dip": {"verdict": "NONE"}}})
            code, out = self.check(wd, self.base, cfg={"require_edge": True})
            self.assertIn("edge: the signal lab rated this setup NONE", out)

    def test_crypto_needs_no_bell_and_no_bracket(self):
        with Workdir() as wd:
            btc = {"id": "o1", "symbol": "BTC/USD", "asset_class": "crypto", "side": "buy", "qty": "0.001",
                   "type": "market", "time_in_force": "gtc",
                   "plan": {"entry": 58813.83, "stop": 52000.0, "target": 72000.0, "setup": "dip"}}
            code, out = self.check(wd, btc, "2026-11-22 03:00")
            self.assertIn("PASS", out)
            self.assertIn("the stop lives in the plan", out)
            code, out = self.check(wd, dict(btc, order_class="bracket"), "2026-11-22 03:00")
            self.assertIn("no bracket orders for crypto", out)
            code, out = self.check(wd, btc, "2026-11-22 03:00", cfg={"allow_crypto": False})
            self.assertIn("crypto is off", out)


if __name__ == "__main__":
    unittest.main()
