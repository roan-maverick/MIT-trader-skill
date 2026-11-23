#!/usr/bin/env python3
# Reviewed for local use
"""mit-trader / var: how much could the whole account lose on a bad day? (L7, Value at Risk)

It values what you hold (mit/portfolio.json) plus, with --include-orders, the
orders waiting in mit/orders.json as if they had filled, then estimates the
1-day loss you should only exceed 1 day in 100 (99% VaR) three ways, as the
lecture does:

  historical   replay the last 500 days of real joint returns on today's positions
  parametric   variance-covariance (normal), on a Ledoit-Wolf shrinkage covariance (L10)
  monte carlo  10,000 correlated normal draws through a Cholesky factor (L2)

and the expected shortfall: the average loss on the days worse than the VaR.
Kupiec's test then checks the method on the past 250 days: did losses beat
the VaR about as often as promised?

Usage:
  var.py run [--include-orders] [--conf 0.99] [--data DIR] [--asof DATE] [--write]
"""

import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402


def positions(cfg, include_orders):
    pf = M.load_json(M.path("portfolio.json")) or {"cash": float(cfg["budget"]), "positions": []}
    pos = {}
    for p in pf.get("positions", []):
        s = M.norm_symbol(p["symbol"])
        pos[s] = pos.get(s, 0.0) + float(p.get("qty", 0))
    cash = float(pf.get("cash", 0))
    added = []
    if include_orders:
        od = M.load_json(M.path("orders.json")) or {}
        for o in od.get("orders", []):
            s = M.norm_symbol(o["symbol"])
            q = float(o["qty"]) * (1 if o["side"] == "buy" else -1)
            pos[s] = pos.get(s, 0.0) + q
            px = float((o.get("plan") or {}).get("entry") or 0)
            cash -= q * px
            added.append(o["id"])
    return {k: v for k, v in pos.items() if abs(v) > 1e-12}, cash, added


def run(cfg, include_orders=False, conf=0.99, data_dir=None, asof=None, window=500, seed=M.SEED, n_mc=10000):
    pos, cash, added = positions(cfg, include_orders)
    if not pos:
        return {"asof": asof, "equity": cash, "positions": {}, "var_hist": 0.0, "es_hist": 0.0,
                "var_param": 0.0, "var_mc": 0.0, "var_pct": 0.0, "note": "no positions: nothing at risk"}
    series, last = {}, {}
    for s in pos:
        d, c = M.closes(M.load_bars(s, data_dir), asof=asof, lookback=window + 251)
        series[s] = (d[1:], M.log_returns(c))
        last[s] = c[-1]
    dates, R = M.align(series)
    syms = sorted(pos)
    value = {s: pos[s] * last[s] for s in syms}
    equity = cash + sum(value.values())
    gross = sum(abs(v) for v in value.values())
    n = len(dates)
    lo = max(0, n - window)  # the VaR window: the last `window` days

    def pnl_on(t):  # a day's P&L, positions held fixed (simple returns from log returns)
        return sum(value[s] * (math.exp(R[s][t]) - 1) for s in syms)

    pnl = [pnl_on(t) for t in range(lo, len(dates))]
    v_h, es_h = M.var_es(pnl, conf)
    rows = [[R[s][t] for s in syms] for t in range(lo, len(dates))]
    S, delta = M.ledoit_wolf(rows) if len(syms) > 1 else ([[M.var([r[0] for r in rows])]], 0.0)
    vvec = [value[s] for s in syms]
    sd_p = math.sqrt(max(M.dot(vvec, M.matvec(S, vvec)), 0))
    z = M.norm_ppf(conf)
    v_p = z * sd_p
    es_p = sd_p * M.norm_pdf(z) / (1 - conf)
    L = M.cholesky(S)
    rng = random.Random(seed)
    mc = []
    for _ in range(n_mc):
        e = [rng.gauss(0, 1) for _ in syms]
        r = M.matvec(L, e)
        mc.append(sum(vvec[i] * (math.exp(r[i]) - 1) for i in range(len(syms))))
    v_mc, es_mc = M.var_es(mc, conf)
    # Kupiec backtest of historical VaR over the last 250 days, each day using the prior window
    exc, n_bt = 0, 0
    daily = [pnl_on(t) for t in range(n)]
    for t in range(max(250, n - 250), n):  # each backtest day needs 250+ days before it
        vt, _ = M.var_es(daily[max(0, t - window):t], conf)
        n_bt += 1
        if -daily[t] > vt:
            exc += 1
    lr, pval = M.kupiec(exc, n_bt, conf) if n_bt else (float("nan"), float("nan"))
    contrib = {}
    if sd_p > 0:
        Sv = M.matvec(S, vvec)
        for i, s in enumerate(syms):
            contrib[s] = vvec[i] * Sv[i] / (sd_p * sd_p)
    return {
        "asof": dates[-1], "confidence": conf, "horizon": "1 day", "window_days": len(pnl),
        "equity": equity, "cash": cash, "gross_exposure": gross, "includes_orders": added,
        "positions": {s: {"qty": pos[s], "price": last[s], "value": value[s]} for s in syms},
        "var_hist": v_h, "es_hist": es_h, "var_param": v_p, "es_param": es_p, "var_mc": v_mc, "es_mc": es_mc,
        "var_pct": max(v_h, v_p, v_mc) / equity * 100 if equity > 0 else float("inf"),
        "shrinkage": delta, "risk_share": contrib,
        "kupiec": {"days": n_bt, "exceptions": exc, "expected": round(n_bt * (1 - conf), 2), "lr": lr, "p": pval},
    }


def show(r, limit):
    if not r["positions"]:
        print("No positions and no orders: nothing at risk.")
        return
    print("Value at Risk, %s, %s confidence, data to %s" % (r["horizon"], M.pct(r["confidence"], 0), r["asof"]))
    print("  equity %s, gross exposure %s%s" % (M.money(r["equity"]), M.money(r["gross_exposure"]),
          " (includes %d proposed order(s))" % len(r["includes_orders"]) if r["includes_orders"] else ""))
    for s, p in r["positions"].items():
        print("    %-8s %s units x %s = %s, %s of the risk" % (s, M.num(p["qty"], 4).rstrip("0").rstrip("."), M.num(p["price"]),
              M.money(p["value"]), M.pct(r["risk_share"].get(s, 0), 0)))
    print("  1-day VaR: historical %s, parametric %s, Monte Carlo %s" % (
        M.money(r["var_hist"]), M.money(r["var_param"]), M.money(r["var_mc"])))
    print("  expected shortfall (average loss beyond the VaR): historical %s, parametric %s" % (
        M.money(r["es_hist"]), M.money(r["es_param"])))
    k = r["kupiec"]
    if k["days"]:
        print("  Kupiec backtest: %d of the last %d days lost more than the VaR (expected %s), p = %s: %s" % (
            k["exceptions"], k["days"], k["expected"], M.num(k["p"], 3),
            "the model holds up" if k["p"] >= 0.05 else "the model understates the risk" if k["exceptions"] > k["expected"] else "the model is too cautious"))
    worst = r["var_pct"]
    print("  worst of the three: %s of equity; your limit is %s%%: %s" % (
        M.pct(worst / 100, 2), limit, "within it" if worst <= limit else "OVER IT"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--include-orders", action="store_true")
    r.add_argument("--conf", type=float)
    r.add_argument("--data"); r.add_argument("--asof"); r.add_argument("--config")
    r.add_argument("--write", action="store_true"); r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = M.load_config(a.config)
    res = run(cfg, a.include_orders, a.conf or float(cfg["var_confidence"]), a.data, a.asof)
    if a.write:
        M.save_json(M.path("var.json"), res)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        show(res, cfg["max_var_pct"])
        if a.write:
            print("Wrote %s" % M.path("var.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
