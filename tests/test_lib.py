# Reviewed for local use
"""The shared math in mit-trader/scripts/mitlib.py, checked against known answers."""

import json
import math
import os
import random
import sys
import unittest

from _load import ROOT, BARS

sys.path.insert(0, os.path.join(ROOT, "mit-trader", "scripts"))
import mitlib as M  # noqa: E402


class Distributions(unittest.TestCase):
    def test_normal(self):
        self.assertAlmostEqual(M.norm_cdf(1.96), 0.975, places=3)
        self.assertAlmostEqual(M.norm_ppf(0.99), 2.326348, places=5)
        self.assertAlmostEqual(M.norm_ppf(0.01), -2.326348, places=5)
        for p in (0.001, 0.2, 0.5, 0.77, 0.999):
            self.assertAlmostEqual(M.norm_cdf(M.norm_ppf(p)), p, places=9)

    def test_t_and_chi2(self):
        self.assertAlmostEqual(M.t_pvalue(2.042, 30), 0.05, places=3)      # t table, 30 df
        self.assertAlmostEqual(M.chi2_sf(3.841, 1), 0.05, places=3)
        self.assertAlmostEqual(M.chi2_sf(18.307, 10), 0.05, places=4)

    def test_bonferroni_bar(self):
        self.assertAlmostEqual(M.bonferroni_t(1), 1.96, places=2)
        self.assertAlmostEqual(M.bonferroni_t(168), 3.62, places=2)


class LinearAlgebra(unittest.TestCase):
    def test_eigen_symmetric(self):
        vals, vecs = M.eig_sym([[4, 1, 0], [1, 3, 1], [0, 1, 2]])
        self.assertAlmostEqual(vals[0], 3 + math.sqrt(3), places=8)
        self.assertAlmostEqual(vals[1], 3.0, places=8)
        self.assertAlmostEqual(vals[2], 3 - math.sqrt(3), places=8)
        A = [[4, 1, 0], [1, 3, 1], [0, 1, 2]]
        Av = M.matvec(A, vecs[0])
        for a, v in zip(Av, vecs[0]):
            self.assertAlmostEqual(a, vals[0] * v, places=8)

    def test_solve_inverse_cholesky(self):
        A = [[4.0, 2.0, 0.6], [2.0, 5.0, 1.0], [0.6, 1.0, 3.0]]
        x = M.solve(A, [1, 2, 3])
        self.assertEqual([round(v, 10) for v in M.matvec(A, x)], [1, 2, 3])
        I = M.matmul(A, M.inv(A))
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(I[i][j], 1.0 if i == j else 0.0, places=10)
        L = M.cholesky(A)
        LL = M.matmul(L, M.transpose(L))
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(LL[i][j], A[i][j], places=10)

    def test_ledoit_wolf_is_a_blend(self):
        rng = random.Random(1)
        R = [[rng.gauss(0, 1) for _ in range(6)] for _ in range(40)]
        S, d = M.ledoit_wolf(R)
        self.assertTrue(0 <= d <= 1)
        self.assertAlmostEqual(S[0][1], S[1][0])


class Regression(unittest.TestCase):
    def test_ols_recovers_a_line(self):
        rng = random.Random(2)
        x = [i / 10.0 for i in range(200)]
        y = [1.5 + 2.0 * v + rng.gauss(0, 0.5) for v in x]
        f = M.ols(y, x)
        self.assertAlmostEqual(f["beta"][0], 1.5, delta=0.2)
        self.assertAlmostEqual(f["beta"][1], 2.0, delta=0.03)
        nw = M.ols(y, x, nw_lags=5)
        self.assertEqual(nw["beta"], f["beta"])

    def test_adf_tells_a_random_walk_from_ar1(self):
        rng = random.Random(3)
        rw, ar = [0.0], [0.0]
        for _ in range(3000):
            rw.append(rw[-1] + rng.gauss(0, 1))
            ar.append(0.8 * ar[-1] + rng.gauss(0, 1))
        self.assertIsNone(M.adf(rw)["reject_at"])
        self.assertEqual(M.adf(ar)["reject_at"], 0.01)
        self.assertAlmostEqual(M.ar1(ar)["half_life"], math.log(0.5) / math.log(0.8), delta=0.5)

    def test_mackinnon_values(self):
        c = M.mackinnon_crit(1, 10 ** 9)
        self.assertAlmostEqual(c[0.05], -2.86154, places=4)
        c2 = M.mackinnon_crit(2, 250)
        self.assertAlmostEqual(c2[0.05], -3.36, places=2)


class Volatility(unittest.TestCase):
    def test_garch_on_nvda(self):
        doc = json.load(open(os.path.join(BARS, "NVDA.json")))
        _, c = M.closes(doc, asof="2026-11-20", lookback=757)
        g = M.garch11(M.log_returns(c))
        self.assertAlmostEqual(g["alpha"], 0.121, delta=0.003)
        self.assertAlmostEqual(g["beta"], 0.841, delta=0.003)
        self.assertLess(g["persistence"], 1)
        fc = M.garch_forecast(g, 30)
        self.assertGreater(fc[0], fc[-1])            # high now, decaying to the long run
        self.assertGreater(fc[-1], g["long_run_var"])

    def test_bridge_probability(self):
        self.assertEqual(M.bridge_cross_prob(0.0, -0.2, -0.1, 0.01), 1.0)   # ended past it
        p = M.bridge_cross_prob(0.0, 0.0, -0.1, 0.01)
        self.assertAlmostEqual(p, math.exp(-2 * 0.1 * 0.1 / 0.01))

    def test_martingale_has_zero_expected_value(self):
        # Doob's optional stopping theorem (L5): stops and targets do not create an edge
        rng = random.Random(M.SEED)
        res = M.first_passage(M.gbm_steps(0.0, 0.02), 20000, 100.0, 95.0, 110.0, 10, rng)
        mean_pnl = M.mean(res["pnl"])
        sd = M.std(res["pnl"]) / math.sqrt(20000)
        self.assertLess(abs(mean_pnl), 3 * sd)


class Options(unittest.TestCase):
    def test_hull_example(self):
        c = M.bs(42, 40, 0.5, 0.10, 0.20)
        p = M.bs(42, 40, 0.5, 0.10, 0.20, "put")
        self.assertAlmostEqual(c["price"], 4.76, places=2)
        self.assertAlmostEqual(p["price"], 0.81, places=2)
        self.assertAlmostEqual(c["price"] - p["price"], 42 - 40 * math.exp(-0.05), places=10)  # parity
        self.assertAlmostEqual(M.implied_vol(c["price"], 42, 40, 0.5, 0.10), 0.20, places=5)


class Portfolio(unittest.TestCase):
    def test_kelly(self):
        self.assertAlmostEqual(M.kelly_binary(0.5, 1), 0.0)
        self.assertAlmostEqual(M.kelly_binary(0.6, 1), 0.2)
        self.assertAlmostEqual(M.kelly_binary(1.0, 1), 1.0)

    def test_risk_parity_equalizes_risk(self):
        S = [[0.04, 0.006, 0.0], [0.006, 0.01, 0.001], [0.0, 0.001, 0.0225]]
        w = M.risk_parity(S)
        rc = M.risk_contributions(S, w)
        for x in rc:
            self.assertAlmostEqual(x, 1 / 3.0, places=4)
        self.assertAlmostEqual(sum(w), 1.0, places=10)

    def test_min_variance_respects_cap(self):
        S = [[0.04, 0.0, 0.0], [0.0, 0.001, 0.0], [0.0, 0.0, 0.09]]
        w = M.min_variance(S, cap=0.5)
        self.assertLessEqual(max(w), 0.5 + 1e-9)
        self.assertAlmostEqual(sum(w), 1.0, places=6)

    def test_almgren_chriss(self):
        ac = M.almgren_chriss(1000, 1.0, 10, 1.0, 0.01, 0.0, 0.0)
        self.assertEqual([round(h) for h in ac["holdings"]], list(range(1000, -1, -100)))  # TWAP
        ac = M.almgren_chriss(1000, 1.0, 10, 1.0, 0.01, 0.0, 0.5)
        self.assertGreater(ac["trades"][0], ac["trades"][-1])                             # front-loaded
        self.assertAlmostEqual(sum(ac["trades"]), 1000, places=6)


class Risk(unittest.TestCase):
    def test_kupiec(self):
        lr, p = M.kupiec(2, 250, 0.99)
        self.assertGreater(p, 0.5)
        lr, p = M.kupiec(12, 250, 0.99)
        self.assertLess(p, 0.01)


class DataAndClock(unittest.TestCase):
    def test_symbols(self):
        for s in ("BTC", "btc/usd", "BTCUSD", "BTC-USD"):
            self.assertEqual(M.norm_symbol(s), "BTC-USD")
        self.assertEqual(M.broker_symbol("BTC"), "BTC/USD")
        self.assertTrue(M.is_crypto("eth"))
        self.assertFalse(M.is_crypto("NVDA"))
        self.assertEqual(M.norm_symbol("brk/b"), "BRK-B")

    def test_parse_yahoo_chart(self):
        doc = json.load(open(os.path.join(ROOT, "tests", "fixtures", "yahoo-AAPL.json")))
        b = M.parse_yahoo_chart(doc, "AAPL")
        self.assertEqual(b["dates"], ["2026-11-18", "2026-11-19", "2026-11-20"])
        self.assertEqual(b["close"], [341.5, 337.2, 342.56])
        self.assertAlmostEqual(b["open"][0], 345.0 * 341.5 / 342.0, places=4)   # OHLC adjusted like the close
        self.assertEqual(b["last"]["price"], 342.56)

    def test_market_session(self):
        at = lambda s: M.market_session(M.ny_now(s))
        self.assertTrue(at("2026-11-23 10:00")[0])
        self.assertFalse(at("2026-11-23 09:00")[0])
        self.assertEqual(at("2026-11-22 12:00")[3], "weekend")
        self.assertEqual(at("2026-11-26 12:00")[3], "NYSE holiday")     # Thanksgiving
        self.assertEqual(at("2026-11-27 12:00")[3], "early close 1:00 PM")
        self.assertFalse(at("2026-11-27 13:30")[0])


if __name__ == "__main__":
    unittest.main()
