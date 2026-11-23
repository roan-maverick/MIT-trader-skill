#!/usr/bin/env python3
"""mit-trader / regression (Signal Lab): is this setup's edge real, or luck?

For one symbol and one setup it looks back over the whole history it has
(5 years by default) and asks three regression questions (L6):

  1. Predictive regression: does today's signal predict the next h-day
     return? r(t, t+h) = a + b * signal(t) + e, with Newey-West errors
     because h-day returns sampled daily overlap.
  2. Event study: every past day the rule fired (no two within h days),
     what happened over the next h days, compared with an ordinary h days?
  3. Out of sample: does the result hold on the last 30% of the history,
     which played no part in judging the first 70%?

Then it raises the bar for luck: if the scanner tried N rules today, a
t-statistic must clear the Bonferroni bar for N tests, not just 2.

Usage:
  signal.py test NVDA --setup dip [--horizon 5] [--n-tests 168] [--data DIR] [--asof DATE] [--write]
  signal.py candidates [--data DIR] [--asof DATE] [--write]     # every candidate in mit/candidates.json
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

Z_WINDOW, Z_ENTRY, TREND_WINDOW, TREND_T = 20, 2.0, 63, 3.0
DIRECTION = {"dip": 1, "trend": 1, "rip": -1, "slide": -1}  # +1: the setup is a buy


def rolling_signal(lp, setup):
    """Signal value for each day (None while the window fills)."""
    n = len(lp)
    out = [None] * n
    if setup in ("dip", "rip"):
        s = s2 = 0.0
        for i in range(n):
            s += lp[i]; s2 += lp[i] * lp[i]
            if i >= Z_WINDOW:
                s -= lp[i - Z_WINDOW]; s2 -= lp[i - Z_WINDOW] ** 2
            if i >= Z_WINDOW - 1:
                m = s / Z_WINDOW
                v = (s2 - Z_WINDOW * m * m) / (Z_WINDOW - 1)
                out[i] = (lp[i] - m) / math.sqrt(v) if v > 1e-14 else 0.0
    else:
        W = TREND_WINDOW
        tbar = (W - 1) / 2.0
        stt = sum((t - tbar) ** 2 for t in range(W))
        for i in range(W - 1, n):
            y = lp[i - W + 1:i + 1]
            yb = sum(y) / W
            b = sum((t - tbar) * (y[t] - yb) for t in range(W)) / stt
            a = yb - b * tbar
            sse = sum((y[t] - a - b * t) ** 2 for t in range(W))
            se = math.sqrt(sse / (W - 2) / stt) if sse > 0 else 1e-12
            out[i] = b / se  # plain OLS t; the scanner uses Newey-West on the latest window
    return out


def fires(setup, s):
    if s is None:
        return False
    if setup == "dip":
        return s <= -Z_ENTRY
    if setup == "rip":
        return s >= Z_ENTRY
    if setup == "trend":
        return s >= TREND_T
    if setup == "slide":
        return s <= -TREND_T
    return False


def tstat(x):
    if len(x) < 2:
        return float("nan")
    sd = M.std(x)
    return M.mean(x) / (sd / math.sqrt(len(x))) if sd > 0 else float("nan")


def analyse(sym, setup, horizon=5, n_tests=1, data_dir=None, asof=None, lookback=1260):
    if setup not in DIRECTION:
        raise ValueError("setup must be one of dip, rip, trend, slide")
    bars = M.load_bars(sym, data_dir)
    dates, px = M.closes(bars, asof=asof, lookback=lookback)
    lp = [math.log(p) for p in px]
    sig = rolling_signal(lp, setup)
    h = horizon
    d = DIRECTION[setup]
    fwd = [lp[i + h] - lp[i] if i + h < len(lp) else None for i in range(len(lp))]
    idx = [i for i in range(len(lp)) if sig[i] is not None and fwd[i] is not None]
    # 1. predictive regression, Newey-West with h-1 lags for the overlap
    ys = [fwd[i] for i in idx]
    xs = [sig[i] for i in idx]
    reg = M.ols(ys, xs, nw_lags=max(h - 1, 1))
    base = M.mean(ys)
    # 2. events, de-clustered: a new event only h days after the last one
    events, last = [], -10 ** 9
    for i in idx:
        if fires(setup, sig[i]) and i - last >= h:
            events.append(i)
            last = i
    ev_ret = [d * fwd[i] for i in events]            # in the trade's direction
    ev_excess = [d * (fwd[i] - base) for i in events]  # beyond an ordinary h days
    # 3. out of sample: split the history 70 / 30 by date
    cut = idx[int(len(idx) * 0.7)] if idx else 0
    ins = [d * (fwd[i] - base) for i in events if i < cut]
    oos = [d * (fwd[i] - base) for i in events if i >= cut]
    bar = M.bonferroni_t(n_tests)
    t_ev = tstat(ev_excess)
    t_reg = reg["t"][1]
    # a dip / rip signal should have a negative slope (low z -> higher return); trends positive
    want_sign = -1 if setup in ("dip", "rip") else 1
    reg_ok = (t_reg * want_sign) >= bar
    ev_ok = t_ev == t_ev and t_ev >= bar
    oos_ok = len(oos) >= 3 and M.mean(oos) > 0
    if (ev_ok or reg_ok) and oos_ok:
        verdict = "EDGE"
    elif (t_ev == t_ev and t_ev >= 1.0) or (t_reg * want_sign) >= 1.0:
        verdict = "WEAK"
    else:
        verdict = "NONE"
    now = sig[-1]
    res = {
        "symbol": M.norm_symbol(sym), "setup": setup, "horizon_days": h, "asof": dates[-1],
        "history": {"from": dates[0], "to": dates[-1], "days": len(dates)},
        "signal_now": round(now, 3) if now is not None else None, "fires_now": fires(setup, now),
        "regression": {"slope": reg["beta"][1], "t_newey_west": round(t_reg, 3), "p": reg["p"][1],
                       "r2": round(reg["r2"], 5), "n": reg["n"], "expected_sign": want_sign},
        "events": {"count": len(events), "mean_return": M.mean(ev_ret) if ev_ret else None,
                   "mean_excess": M.mean(ev_excess) if ev_excess else None,
                   "hit_rate": (sum(1 for x in ev_ret if x > 0) / len(ev_ret)) if ev_ret else None,
                   "t_excess": round(t_ev, 3) if t_ev == t_ev else None,
                   "dates": [dates[i] for i in events][-12:]},
        "baseline_h_day_return": base,
        "out_of_sample": {"split_date": dates[cut] if idx else None, "in_events": len(ins),
                          "in_mean_excess": M.mean(ins) if ins else None, "out_events": len(oos),
                          "out_mean_excess": M.mean(oos) if oos else None},
        "n_tests": n_tests, "t_bar": round(bar, 3), "verdict": verdict,
    }
    return res


def explain(r):
    e, g, o = r["events"], r["regression"], r["out_of_sample"]
    lines = ["%s %s, %d-day horizon, %s to %s (%d days)" % (r["symbol"], r["setup"], r["horizon_days"],
             r["history"]["from"], r["history"]["to"], r["history"]["days"])]
    lines.append("  signal now %s (%s)" % (M.num(r["signal_now"]), "fires" if r["fires_now"] else "does not fire"))
    if e["count"]:
        lines.append("  past events: %d. After them the %d-day return averaged %s (an ordinary %d days: %s), "
                     "won %s of the time, t = %s" % (
                         e["count"], r["horizon_days"], M.pct(e["mean_return"], 2), r["horizon_days"],
                         M.pct(r["baseline_h_day_return"], 2), M.pct(e["hit_rate"], 0), M.num(e["t_excess"])))
    else:
        lines.append("  the rule never fired in this history")
    lines.append("  predictive regression: t = %s (Newey-West), R^2 = %s" % (M.num(g["t_newey_west"]), M.num(g["r2"], 4)))
    if o["out_events"]:
        lines.append("  out of sample (after %s): %d events, excess %s vs %s before" % (
            o["split_date"], o["out_events"], M.pct(o["out_mean_excess"], 2), M.pct(o["in_mean_excess"], 2)))
    lines.append("  bar for luck: |t| >= %s (%d tests today)" % (M.num(r["t_bar"]), r["n_tests"]))
    word = {"EDGE": "EDGE: it cleared the bar and held up out of sample.",
            "WEAK": "WEAK: it leans the right way but does not clear the bar. Could be luck.",
            "NONE": "NONE: no evidence this setup pays. Treat it as a coin flip or worse."}[r["verdict"]]
    lines.append("  verdict " + word)
    return "\n".join(lines)


def save(results, n_tests):
    p = M.path("signals.json")
    doc = M.load_json(p, {}) or {}
    doc.setdefault("results", {})
    for r in results:
        doc["results"]["%s:%s" % (r["symbol"], r["setup"])] = r
        doc["asof"] = r["asof"]
    doc["n_tests"] = n_tests
    M.save_json(p, doc)
    return p


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test")
    t.add_argument("symbol")
    t.add_argument("--setup", default="dip", choices=sorted(DIRECTION))
    t.add_argument("--n-tests", type=int, default=1)
    c = sub.add_parser("candidates")
    for s in (t, c):
        s.add_argument("--horizon", type=int)
        s.add_argument("--data")
        s.add_argument("--asof")
        s.add_argument("--config")
        s.add_argument("--write", action="store_true")
        s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    cfg = M.load_config(a.config)
    h = a.horizon or int(cfg["horizon_days"])
    if a.cmd == "test":
        jobs, n_tests = [(a.symbol, a.setup)], a.n_tests
    else:
        doc = M.load_json(M.path("candidates.json"))
        if not doc:
            print("No mit/candidates.json yet. Run the scanner first.")
            return 1
        jobs = [(c["symbol"], c["setup"]) for c in doc["candidates"]]
        n_tests = doc.get("n_tests", len(jobs))
    results = [analyse(s, st, h, n_tests, a.data, a.asof) for s, st in jobs]
    if a.write:
        where = save(results, n_tests)
    if a.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        for r in results:
            print(explain(r))
        if a.cmd == "candidates":
            n = {k: sum(1 for r in results if r["verdict"] == k) for k in ("EDGE", "WEAK", "NONE")}
            print("\n%d tested: %d EDGE, %d WEAK, %d NONE." % (len(results), n["EDGE"], n["WEAK"], n["NONE"]))
        if a.write:
            print("Wrote %s" % where)
    return 0


if __name__ == "__main__":
    sys.exit(main())
