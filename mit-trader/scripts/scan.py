#!/usr/bin/env python3
# Reviewed for local use
"""mit-trader / scanner: scan a universe of stocks, ETFs and coins for statistical setups.

Setups (all on daily closes):
  dip    the price is 2+ standard deviations below its 20-day mean (L3 z-score; L8 mean reversion)
  rip    2+ standard deviations above it (a short setup; only traded if allow_short)
  trend  the 63-day log-price regression on time has a t-statistic of 3 or more (L6)
  slide  the same t-statistic at -3 or less (a falling trend: a warning, not a buy)

Usage:
  scan.py run [--tickers AAPL,NVDA,BTC] [--data DIR] [--asof 2026-11-20] [--top 10] [--write] [--json]
  scan.py stats NVDA [--data DIR] [--asof DATE]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

Z_WINDOW = 20
TREND_WINDOW = 63
Z_ENTRY = 2.0
TREND_T = 3.0


def trend_t(logp, nw_lags=5):
    """t statistic of the slope of log price on time, Newey-West errors (L6)."""
    n = len(logp)
    fit = M.ols(logp, [float(i) for i in range(n)], nw_lags=nw_lags)
    return fit["beta"][1], fit["t"][1]


def stats_for(sym, data_dir=None, asof=None):
    bars = M.load_bars(sym, data_dir)
    dates, px = M.closes(bars, asof=asof, lookback=300)
    if len(px) < TREND_WINDOW + 5:
        raise RuntimeError("%s: only %d days of history" % (sym, len(px)))
    lp = [math.log(p) for p in px]
    w = lp[-Z_WINDOW:]
    mu, sd = M.mean(w), M.std(w)
    z = (lp[-1] - mu) / sd if sd > 0 else 0.0
    rets = M.log_returns(px)
    ann = 365 if M.is_crypto(sym) else 252
    vol20 = M.std(rets[-20:]) * math.sqrt(ann)
    slope, tt = trend_t(lp[-TREND_WINDOW:])
    ou = M.ou_fit(lp[-120:])
    setup = None
    if z <= -Z_ENTRY:
        setup = "dip"
    elif z >= Z_ENTRY:
        setup = "rip"
    elif tt >= TREND_T:
        setup = "trend"
    elif tt <= -TREND_T:
        setup = "slide"
    score = abs(z) if setup in ("dip", "rip") else abs(tt) / 1.5 if setup else 0.0
    return {
        "symbol": M.norm_symbol(sym), "asset_class": M.asset_class(sym), "date": dates[-1],
        "close": px[-1], "z20": round(z, 3), "mean20": round(math.exp(mu), 4),
        "ret_5d": round(px[-1] / px[-6] - 1, 4), "ret_21d": round(px[-1] / px[-22] - 1, 4),
        "vol20_ann": round(vol20, 4), "trend_t63": round(tt, 2), "trend_ann": round(slope * ann, 4),
        "half_life_days": round(ou["half_life"], 1) if ou["half_life"] != float("inf") else None,
        "setup": setup, "score": round(score, 3),
    }


def describe(s):
    if s["setup"] == "dip":
        why = "%.2f std below its 20-day mean (%s)" % (-s["z20"], M.num(s["mean20"]))
    elif s["setup"] == "rip":
        why = "%.2f std above its 20-day mean (%s)" % (s["z20"], M.num(s["mean20"]))
    elif s["setup"] == "trend":
        why = "uptrend, t = %.1f over 63 days" % s["trend_t63"]
    elif s["setup"] == "slide":
        why = "downtrend, t = %.1f over 63 days" % s["trend_t63"]
    else:
        why = "no setup"
    return "%-8s %-6s close %s  5d %s  21d %s  vol %s  %s" % (
        s["symbol"], s["setup"] or "-", M.num(s["close"]), M.pct(s["ret_5d"]), M.pct(s["ret_21d"]),
        M.pct(s["vol20_ann"], 0), why)


def cmd_run(a):
    cfg = M.load_config(a.config)
    tickers = [M.norm_symbol(t) for t in (a.tickers.split(",") if a.tickers else cfg["universe"])]
    stats, skipped = [], []
    for t in tickers:
        try:
            stats.append(stats_for(t, a.data, a.asof))
        except Exception as e:  # missing data must not stop the scan
            skipped.append("%s (%s)" % (t, str(e).split(":")[0] if a.data else e))
    cands = sorted([s for s in stats if s["setup"]], key=lambda s: -s["score"])
    if a.top:
        cands = cands[:a.top]
    asof = max((s["date"] for s in stats), default=a.asof)
    out = {"asof": asof, "scanned": len(stats), "n_tests": len(stats) * 4, "skipped": skipped,
           "rules": {"z_window": Z_WINDOW, "z_entry": Z_ENTRY, "trend_window": TREND_WINDOW, "trend_t": TREND_T},
           "candidates": cands, "stats": stats}
    if a.write:
        M.save_json(M.path("candidates.json"), out)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print("Scanned %d symbols, data to %s. %d setups:" % (len(stats), asof, len([s for s in stats if s["setup"]])))
    for s in cands:
        print("  " + describe(s))
    if not cands:
        print("  none today. No setup is a fine answer.")
    if skipped:
        print("Skipped: " + ", ".join(skipped))
    print("Each symbol was checked against 4 rules, %d tests in all; the signal lab uses that count "
          "so a lucky-looking result is not mistaken for an edge." % (len(stats) * 4))
    if a.write:
        print("Wrote %s" % M.path("candidates.json"))
    return 0


def cmd_stats(a):
    s = stats_for(a.symbol, a.data, a.asof)
    if a.json:
        print(json.dumps(s, indent=2))
    else:
        print(describe(s))
        print("  OU half-life of the log price over 120 days: %s days" % (s["half_life_days"] or "none (no pull back)"))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "stats"):
        s = sub.add_parser(name)
        if name == "stats":
            s.add_argument("symbol")
        else:
            s.add_argument("--tickers")
            s.add_argument("--top", type=int, default=0)
            s.add_argument("--write", action="store_true")
        s.add_argument("--data", help="folder of SYMBOL.json bars (offline)")
        s.add_argument("--asof", help="use history up to this date, YYYY-MM-DD")
        s.add_argument("--config")
        s.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    return {"run": cmd_run, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
