#!/usr/bin/env python3
# Reviewed for local use
"""mit-trader / execution: how to split a big order so it does not move the price against you (L22).

Lecture 22 (Calculus of Variations and its Application in FX Execution)
poses the trader's problem: sell X over time T. Trade fast and you pay market
impact; trade slow and the price wanders while you wait. Minimizing
  expected cost + lambda * variance of cost
over every possible trading path is a calculus-of-variations problem. Its
Euler-Lagrange equation is x'' = kappa^2 x, so the optimal holdings follow
  x(t) = X sinh(kappa (T - t)) / sinh(kappa T)
(the Almgren-Chriss solution). kappa grows with risk aversion and volatility
and shrinks with impact: a nervous trader front-loads, a patient one goes
evenly (kappa -> 0 is a straight line, TWAP).

Usage:
  execution.py plan NVDA --qty 20000 [--side buy] [--hours 6.5] [--slices 13]
                   [--adv 250000000] [--urgency 1] [--data DIR] [--asof DATE] [--write]
  execution.py plan --from-orders [--write]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

SMALL = 0.005  # under 0.5% of a day's volume: one order is fine


def plan(sym, qty, side="buy", hours=6.5, slices=13, adv=None, urgency=1.0, data_dir=None, asof=None):
    bars = M.load_bars(sym, data_dir)
    dates, px = M.closes(bars, asof=asof, lookback=61)
    r = M.log_returns(px)
    price = px[-1]
    day_hours = 24.0 if M.is_crypto(sym) else 6.5
    sig_day = M.std(r[-20:]) * price  # $ per share per day
    vols = [v for v in (bars.get("volume") or [])[-20:] if v]
    if adv is None and vols:
        adv = M.mean(vols)
    if not adv:
        raise RuntimeError("no volume in the data: pass --adv (average daily volume in shares or coins)")
    part = qty / adv
    T = hours / day_hours  # in days
    # temporary impact: trading 10% of a day's volume in one day costs about 0.1 sigma per share
    eta = 0.1 * sig_day / (0.1 * adv)
    gamma = 0.1 * sig_day / adv  # permanent impact, smaller
    # urgency = kappa * T, a dial without units: 0 is even slices, 1 leans early, 3+ is front-loaded.
    # It sets the risk aversion: kappa^2 = lambda sigma^2 / eta  ->  lambda = kappa^2 eta / sigma^2
    kappa = urgency / T
    lam = kappa * kappa * eta / (sig_day * sig_day) if sig_day > 0 else 0.0
    ac = M.almgren_chriss(qty, T, slices, sig_day, eta, gamma, lam)
    twap = M.almgren_chriss(qty, T, slices, sig_day, eta, gamma, 0.0)
    step_min = hours * 60 / slices
    sched = []
    for j, n in enumerate(ac["trades"]):
        sched.append({"slice": j + 1, "minute": round(j * step_min), "qty": round(n, 6 if M.is_crypto(sym) else 0)})
    # whole shares: put rounding left-overs in the last slice
    if not M.is_crypto(sym):
        diff = int(qty) - int(sum(s["qty"] for s in sched))
        sched[-1]["qty"] += diff
    return {"symbol": M.norm_symbol(sym), "side": side, "qty": qty, "price": price, "asof": dates[-1],
            "adv": adv, "participation": part, "hours": hours, "slices": slices, "kappa": ac["kappa"],
            "daily_vol_usd": sig_day, "urgency": urgency, "risk_aversion": lam,
            "expected_cost_usd": ac["expected_cost"], "cost_sd_usd": math.sqrt(ac["variance"]),
            "twap_cost_usd": twap["expected_cost"], "twap_sd_usd": math.sqrt(twap["variance"]),
            "one_order": part < SMALL, "schedule": sched}


def show(p):
    print("%s %s %s (%s of a day's volume, %s at %s)" % (p["side"], M.num(p["qty"], 0), p["symbol"],
          M.pct(p["participation"], 2), M.money(p["qty"] * p["price"]), M.num(p["price"])))
    if p["one_order"]:
        print("  Small next to the market: one order is fine. Splitting would only add waiting risk.")
        return
    print("  over %s hours in %d slices, urgency %s (kappa x T; 0 = even slices)" % (p["hours"], p["slices"], p["urgency"]))
    print("  optimal: expected impact cost %s, give or take %s" % (M.money(p["expected_cost_usd"]), M.money(p["cost_sd_usd"])))
    print("  even slices (TWAP): %s, give or take %s" % (M.money(p["twap_cost_usd"]), M.money(p["twap_sd_usd"])))
    for s in p["schedule"]:
        print("    +%3d min  %s" % (s["minute"], M.num(s["qty"], 0)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("symbol", nargs="?")
    p.add_argument("--qty", type=float)
    p.add_argument("--side", default="buy", choices=["buy", "sell"])
    p.add_argument("--hours", type=float, default=6.5)
    p.add_argument("--slices", type=int, default=13)
    p.add_argument("--adv", type=float)
    p.add_argument("--urgency", type=float, default=1.0, help="0 = even slices (TWAP), 1 = lean early, 3+ = front-load")
    p.add_argument("--from-orders", action="store_true")
    p.add_argument("--data"); p.add_argument("--asof")
    p.add_argument("--write", action="store_true"); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    jobs = []
    if a.from_orders:
        for o in (M.load_json(M.path("orders.json")) or {}).get("orders", []):
            jobs.append((o["symbol"], float(o["qty"]), o["side"]))
    else:
        if not a.symbol or not a.qty:
            ap.error("give a symbol and --qty, or --from-orders")
        jobs.append((a.symbol, a.qty, a.side))
    res = []
    for sym, q, side in jobs:
        try:
            res.append(plan(sym, q, side, a.hours, a.slices, a.adv, a.urgency, a.data, a.asof))
        except RuntimeError as e:
            print("%s: %s" % (sym, e))
    if a.write:
        M.save_json(M.path("schedule.json"), {"schedules": res})
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for r in res:
            show(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
