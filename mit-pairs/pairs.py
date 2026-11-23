#!/usr/bin/env python3
"""mit-pairs: statistical arbitrage on two assets that move together (L11, L12).

Two prices can each wander like random walks and still be tied together: a
combination of them, the spread, keeps coming back to its mean. That is
cointegration (L12; the lecture's own example is the law of one price for
equivalent assets). The Engle-Granger test:

  1. regress log A on log B: log A = a + beta log B + spread
  2. run an ADF unit-root test (L8) on the spread, with Engle-Granger critical values
  3. if the spread is stationary, fit it as an Ornstein-Uhlenbeck process (L21) to get
     its half-life, and measure how far it is from its mean now (z-score)

The hedge ratio drifts over time; a Kalman filter (L12) tracks it.

Usage:
  pairs.py scan [--groups semis,banks] [--window 252] [--data DIR] [--asof DATE] [--write]
  pairs.py test GLD GDX [--window 252] [--data DIR] [--asof DATE]
  pairs.py plan GLD GDX [--entry-z 2] [--stop-z 1.5] [--data DIR] [--asof DATE] [--write]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

GROUPS = {
    "megacap": ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
    "semis": ["NVDA", "AMD", "AVGO", "MU", "QCOM", "INTC", "SOXX"],
    "chip_equipment": ["AMAT", "LRCX", "KLAC"],
    "banks": ["JPM", "GS", "WFC", "KRE"],
    "staples": ["PEP", "PG", "COST", "JNJ"],
    "energy": ["CVX", "XLE"],
    "gold": ["GLD", "GDX", "NEM"],
    "bonds": ["TLT", "IEF", "LQD"],
    "indexes": ["SPY", "QQQ", "IWM"],
    "crypto": ["BTC-USD", "ETH-USD"],
}


def series(a, b, data_dir, asof, window):
    s = {}
    for x in (a, b):
        d, c = M.closes(M.load_bars(x, data_dir), asof=asof, lookback=window + 20)
        s[M.norm_symbol(x)] = (d, [math.log(v) for v in c])
    dates, al = M.align(s)
    dates = dates[-window:]
    return dates, al[M.norm_symbol(a)][-window:], al[M.norm_symbol(b)][-window:]


def test(a, b, data_dir=None, asof=None, window=252):
    a, b = M.norm_symbol(a), M.norm_symbol(b)
    dates, la, lb = series(a, b, data_dir, asof, window)
    fit = M.ols(la, lb)
    alpha, beta = fit["beta"]
    spread = fit["resid"]
    eg = M.adf(spread, lags=1, n_vars=2)
    ou = M.ou_fit(spread)
    sd = M.std(spread)
    z = (spread[-1] - M.mean(spread)) / sd
    kal = M.kalman_beta(la, lb, delta=1e-5)
    return {"a": a, "b": b, "asof": dates[-1], "days": len(dates), "hedge_ratio": beta, "intercept": alpha,
            "corr_returns": M.corr(M.log_returns([math.exp(x) for x in la]), M.log_returns([math.exp(x) for x in lb])),
            "adf_stat": eg["stat"], "crit_5pct": eg["crit"][0.05], "cointegrated_at": eg["reject_at"],
            "half_life_days": ou["half_life"], "spread_sd": sd, "z_now": z, "spread_now": spread[-1],
            "spread_mean": M.mean(spread), "ou": {"kappa": ou["kappa"], "theta": ou["theta"], "sigma": ou["sigma"]},
            "kalman_beta_now": kal["beta"][-1], "price_a": math.exp(la[-1]), "price_b": math.exp(lb[-1])}


def best_orientation(a, b, data_dir, asof, window):
    r1 = test(a, b, data_dir, asof, window)
    r2 = test(b, a, data_dir, asof, window)
    return r1 if r1["adf_stat"] <= r2["adf_stat"] else r2


def line(r):
    co = ("yes, %d%% level" % round(100 * r["cointegrated_at"])) if r["cointegrated_at"] else "no"
    hl = M.num(r["half_life_days"], 1) if r["half_life_days"] != float("inf") else "none"
    return "%-8s vs %-8s hedge %5.2f  ADF %6.2f (5%%: %5.2f) cointegrated: %-12s half-life %5s d  z now %+5.2f" % (
        r["a"], r["b"], r["hedge_ratio"], r["adf_stat"], r["crit_5pct"], co, hl, r["z_now"])


def make_plan(r, entry_z=2.0, stop_z=1.5):
    z = r["z_now"]
    sd = r["spread_sd"]
    side = "buy" if z < 0 else "sell"  # buy the spread (long A, short B) when it is cheap
    sign = -1 if side == "buy" else 1
    stop_level = z + sign * stop_z     # further from the mean
    hl = r["half_life_days"] if r["half_life_days"] != float("inf") else 60
    horizon = int(min(max(round(2 * hl), 5), 60))
    return {
        "symbol": r["a"], "pair_with": r["b"], "asset_class": "us_equity", "setup": "pair", "side": side,
        "asof": r["asof"], "horizon_days": horizon, "hedge_ratio": r["hedge_ratio"],
        "price_a": round(r["price_a"], 2), "price_b": round(r["price_b"], 2),
        "entry_z": round(z, 3), "target_z": 0.0, "stop_z": round(stop_level, 3),
        "spread_now": r["spread_now"], "spread_target": r["spread_mean"],
        "spread_stop": r["spread_mean"] + stop_level * sd, "spread_sd": sd, "ou": r["ou"],
        "max_loss_per_unit": abs(stop_level - z) * sd,  # $ lost per $1 of leg A if the spread hits the stop
        "fires": abs(z) >= entry_z, "cointegrated_at": r["cointegrated_at"], "half_life_days": r["half_life_days"],
        "entry": None, "stop": None, "target": None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan"); sc.add_argument("--groups")
    t = sub.add_parser("test"); t.add_argument("a"); t.add_argument("b")
    p = sub.add_parser("plan"); p.add_argument("a"); p.add_argument("b")
    p.add_argument("--entry-z", type=float, default=2.0); p.add_argument("--stop-z", type=float, default=1.5)
    for s in (sc, t, p):
        s.add_argument("--window", type=int, default=252)
        s.add_argument("--data"); s.add_argument("--asof")
        s.add_argument("--write", action="store_true"); s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "scan":
        groups = a.groups.split(",") if a.groups else list(GROUPS)
        res, n = [], 0
        for g in groups:
            syms = GROUPS[g]
            for i in range(len(syms)):
                for j in range(i + 1, len(syms)):
                    try:
                        r = best_orientation(syms[i], syms[j], a.data, a.asof, a.window)
                    except Exception:
                        continue
                    n += 1
                    r["group"] = g
                    res.append(r)
        hits = [r for r in res if r["cointegrated_at"] and r["cointegrated_at"] <= 0.05]
        trade = [r for r in hits if abs(r["z_now"]) >= 2 and r["half_life_days"] <= 30]
        out = {"asof": max((r["asof"] for r in res), default=None), "pairs_tested": n,
               "cointegrated": hits, "tradeable_now": trade}
        if a.write:
            M.save_json(M.path("pairs.json"), out)
        if a.json:
            print(json.dumps(out, indent=2, default=str))
            return 0
        print("Tested %d pairs within %d groups. Cointegrated at 5%%: %d. By luck alone about %d would pass." % (
            n, len(groups), len(hits), round(0.05 * n)))
        for r in sorted(hits, key=lambda r: r["adf_stat"]):
            print("  " + line(r))
        print("Stretched now (|z| >= 2, half-life <= 30 days): %d" % len(trade))
        for r in trade:
            print("  " + line(r))
        return 0
    r = test(a.a, a.b, a.data, a.asof, a.window)
    if a.cmd == "test":
        if a.json:
            print(json.dumps(r, indent=2, default=str))
        else:
            print(line(r))
            print("  Kalman hedge ratio now %.2f (static %.2f); daily returns correlation %.2f" % (
                r["kalman_beta_now"], r["hedge_ratio"], r["corr_returns"]))
        return 0
    pl = make_plan(r, a.entry_z, a.stop_z)
    if a.write:
        doc = M.load_json(M.path("plan.json"), {}) or {}
        plans = [x for x in doc.get("plans", []) if not (x["symbol"] == pl["symbol"] and x.get("pair_with") == pl["pair_with"])]
        plans.append(pl)
        M.save_json(M.path("plan.json"), {"plans": plans, "asof": pl["asof"]})
    if a.json:
        print(json.dumps(pl, indent=2, default=str))
    else:
        print(line(r))
        act = "buy %s, sell %s" % (pl["symbol"], pl["pair_with"]) if pl["side"] == "buy" else "sell %s, buy %s" % (pl["symbol"], pl["pair_with"])
        print("Plan: %s (%s of %s for each $1 of %s); z %+.2f -> target 0, stop %+.2f; horizon %d days" % (
            act, M.num(abs(pl["hedge_ratio"])), pl["pair_with"], pl["symbol"], pl["entry_z"], pl["stop_z"], pl["horizon_days"]))
        print("  risk: %s per $1 of %s if the spread reaches the stop" % (M.money(pl["max_loss_per_unit"]), pl["symbol"]))
        if not pl["fires"]:
            print("  note: |z| is under %s, so the rule does not fire today" % a.entry_z)
        if not pl["cointegrated_at"]:
            print("  warning: not cointegrated at 10%: the spread may never come back")
        if a.write:
            print("Wrote the pair plan into %s. Next: /mit-montecarlo run %s" % (M.path("plan.json"), pl["symbol"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
