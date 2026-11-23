#!/usr/bin/env python3
"""mit-trader / hunt: overnight research. Hunts for strategies that really paid, with the course's statistics.

It tests a library of trading rules built from the course (mean reversion, L8;
trend regressions, L6; volatility regimes, L9; breakouts) in many variants,
on every symbol of the universe at once, and keeps only the ones that pass
all of these:

  1. Pooled event study (L6): every past day a rule fired on any symbol, the
     next h-day return in the trade's direction, minus that symbol's ordinary
     h-day return, minus a round-trip trading cost.
  2. Clustered errors: events on the same week move together (a market-wide
     selloff fires on many stocks at once), so returns are averaged per week
     before the t-statistic is taken. Otherwise one bad week looks like 40 trades.
  3. Walk-forward: rules are judged on the first 70% of history (in-sample) and
     must still pay on the last 30% (out-of-sample), which played no part.
  4. Multiple testing: with ~50 variants, some look great by luck.
     Benjamini-Hochberg keeps the share of false discoveries under 10%;
     Bonferroni (stricter) is reported too.

The approved rules are the trading bot's playbook (mit/strategies.json).
`today` lists which approved rules fire on the latest day.

Usage:
  hunt.py run [--tickers A,B] [--lookback 2520] [--cost-bps 10] [--fdr 0.10] [--data DIR|BUNDLE] [--asof DATE] [--write]
  hunt.py today [--data DIR] [--asof DATE] [--write]      # fresh signals from the approved rules
  hunt.py show                                            # the playbook
"""

import argparse
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

HORIZONS = (5, 10, 21)
SPLIT = 0.7


def library():
    """The rule variants. id, family, params, direction (+1 buy, -1 short), lecture."""
    out = []
    for w in (10, 20, 50):
        for k in (1.5, 2.0, 2.5):
            out.append({"family": "dip", "params": {"window": w, "z": -k}, "dir": 1, "lecture": "L3, L8",
                        "rule": "close %.1f+ std below its %d-day mean" % (k, w)})
    for k in (2.0, 2.5):
        out.append({"family": "rip", "params": {"window": 20, "z": k}, "dir": -1, "lecture": "L3, L8",
                    "rule": "close %.1f+ std above its 20-day mean (short)" % k})
    for w in (63, 126):
        for k in (2.0, 3.0):
            out.append({"family": "trend", "params": {"window": w, "t": k}, "dir": 1, "lecture": "L6",
                        "rule": "%d-day log-price trend with t >= %.0f" % (w, k)})
    out.append({"family": "breakout", "params": {"window": 252}, "dir": 1, "lecture": "L5, L17",
                "rule": "close at a new 252-day high"})
    out.append({"family": "calm", "params": {"ma": 200, "ratio": 0.8}, "dir": 1, "lecture": "L9",
                "rule": "above its 200-day mean while 20-day vol < 0.8 x 1-year vol"})
    variants = []
    for base in out:
        for h in HORIZONS:
            v = dict(base, horizon=h)
            v["id"] = "%s-%s-h%d" % (base["family"], "-".join("%s%s" % (k[0], str(p).replace("-", "m"))
                                                            for k, p in sorted(base["params"].items())), h)
            variants.append(v)
    return variants


# --------------------------------------------------------------- signals

def zscores(lp, w):
    n, out = len(lp), [None] * len(lp)
    s = s2 = 0.0
    for i in range(n):
        s += lp[i]; s2 += lp[i] * lp[i]
        if i >= w:
            s -= lp[i - w]; s2 -= lp[i - w] ** 2
        if i >= w - 1:
            m = s / w
            v = (s2 - w * m * m) / (w - 1)
            out[i] = (lp[i] - m) / math.sqrt(v) if v > 1e-14 else 0.0
    return out


def trend_t(lp, w):
    """Rolling OLS t-statistic of log price on time, O(1) per day with running sums (L6)."""
    n, out = len(lp), [None] * len(lp)
    tbar = (w - 1) / 2.0
    stt = w * (w * w - 1) / 12.0
    sy = syy = sjy = 0.0
    for i in range(n):
        y = lp[i]
        sy += y; syy += y * y; sjy += i * y
        if i >= w:
            yo = lp[i - w]
            sy -= yo; syy -= yo * yo; sjy -= (i - w) * yo
        if i >= w - 1:
            start = i - w + 1
            sty = sjy - start * sy               # sum of (relative time) x y
            ybar = sy / w
            b = (sty - tbar * sy) / stt
            sse = syy - w * ybar * ybar - b * b * stt
            se = math.sqrt(max(sse, 1e-18) / (w - 2) / stt)
            out[i] = b / se
    return out


def fire_series(px, fam, p, cache):
    lp = cache.setdefault("lp", [math.log(x) for x in px])
    n = len(px)
    if fam in ("dip", "rip"):
        z = cache.setdefault(("z", p["window"]), zscores(lp, p["window"]))
        if fam == "dip":
            return [z[i] is not None and z[i] <= p["z"] for i in range(n)]
        return [z[i] is not None and z[i] >= p["z"] for i in range(n)]
    if fam == "trend":
        t = cache.setdefault(("t", p["window"]), trend_t(lp, p["window"]))
        return [t[i] is not None and t[i] >= p["t"] for i in range(n)]
    if fam == "breakout":
        w = p["window"]
        out = [False] * n
        for i in range(w, n):
            out[i] = px[i] >= max(px[i - w:i])
        return out
    if fam == "calm":
        r = [0.0] + M.log_returns(px)
        out = [False] * n
        ma = p["ma"]
        s = sum(px[:ma])
        for i in range(ma, n):
            s += px[i] - px[i - ma]
            if i < 252:
                continue
            v20 = M.std(r[i - 19:i + 1])
            v252 = M.std(r[i - 251:i + 1])
            out[i] = px[i] > s / ma and v20 < p["ratio"] * v252
        return out
    raise ValueError(fam)


# --------------------------------------------------------------- statistics

def week_key(d):
    y, w, _ = dt.date(int(d[:4]), int(d[5:7]), int(d[8:10])).isocalendar()
    return "%d-%02d" % (y, w)


def clustered(events):
    """Average by entry week, then t over weeks."""
    by = {}
    for d, x in events:
        by.setdefault(week_key(d), []).append(x)
    wk = [M.mean(v) for v in by.values()]
    if len(wk) < 3:
        return {"weeks": len(wk), "mean": M.mean(wk) if wk else None, "t": None}
    sd = M.std(wk)
    return {"weeks": len(wk), "mean": M.mean(wk), "t": M.mean(wk) / (sd / math.sqrt(len(wk))) if sd > 0 else None}


def bh_select(pvals, q):
    """Benjamini-Hochberg: indices discovered at false discovery rate q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    k = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            k = rank
    return set(order[:k])


def load_universe(tickers, data_dir, asof, lookback):
    data, skipped = {}, []
    for t in tickers:
        try:
            d, c = M.closes(M.load_bars(t, data_dir), asof=asof, lookback=lookback)
            if len(c) < 300:
                skipped.append(t); continue
            data[M.norm_symbol(t)] = (d, c)
        except Exception:
            skipped.append(t)
    return data, skipped


def run(tickers, data_dir=None, asof=None, lookback=2520, cost_bps=10.0, fdr=0.10):
    data, skipped = load_universe(tickers, data_dir, asof, lookback)
    lib = library()
    all_dates = sorted(set(d for ds, _ in data.values() for d in ds))
    split_date = all_dates[int(len(all_dates) * SPLIT)]
    cost = 2 * cost_bps / 1e4
    caches = {s: {} for s in data}
    fires = {}
    results = []
    for v in lib:
        h, d = v["horizon"], v["dir"]
        ins, oos, raw_trades = [], [], []
        key = (v["family"], json.dumps(v["params"], sort_keys=True))
        for s, (ds, px) in data.items():
            if (s, key) not in fires:
                fires[(s, key)] = fire_series(px, v["family"], v["params"], caches[s])
            f = fires[(s, key)]
            lp = caches[s]["lp"]
            n = len(px)
            fw = [lp[i + h] - lp[i] for i in range(n - h)]
            base = M.mean(fw)
            last = -10 ** 9
            for i in range(n - h):
                if f[i] and i - last >= h:
                    last = i
                    trade = d * fw[i] - cost
                    exc = d * (fw[i] - base) - cost
                    raw_trades.append(trade)
                    (ins if ds[i] < split_date else oos).append((ds[i], exc))
        ci, co = clustered(ins), clustered(oos)
        t_in = ci["t"]
        p_in = (1 - M.norm_cdf(t_in)) if t_in is not None else 1.0  # one-sided: does it beat ordinary days?
        results.append(dict(v, events_in=len(ins), events_out=len(oos), weeks_in=ci["weeks"], weeks_out=co["weeks"],
                            excess_in=ci["mean"], t_in=t_in, p_in=p_in, excess_out=co["mean"], t_out=co["t"],
                            trade_mean=M.mean(raw_trades) if raw_trades else None,
                            hit_rate=(sum(1 for x in raw_trades if x > 0) / len(raw_trades)) if raw_trades else None))
    found = bh_select([r["p_in"] for r in results], fdr)
    bonf = M.bonferroni_t(len(results)) / 1.0
    for i, r in enumerate(results):
        r["bh_discovery"] = i in found
        r["bonferroni"] = (r["t_in"] or 0) >= M.norm_ppf(1 - 0.05 / len(results))
        oos_ok = r["events_out"] >= 10 and r["excess_out"] is not None and r["excess_out"] > 0 and (r["t_out"] or 0) >= 1.0
        enough = r["events_in"] >= 30
        if r["bh_discovery"] and oos_ok and enough:
            r["status"] = "APPROVED"
        elif r["bh_discovery"]:
            r["status"] = "FAILED OUT OF SAMPLE"
        else:
            r["status"] = "REJECTED"
        cred = min(max((r["t_in"] or 0) / M.norm_ppf(1 - 0.05 / len(results)), 0.0), 1.0)
        r["edge"] = {"per_trade": (r["excess_out"] or 0) * cred if r["status"] == "APPROVED" else 0.0,
                     "credibility": cred, "horizon_days": r["horizon"],
                     "source": "out-of-sample excess %+.2f%% per trade x credibility %.2f" % (100 * (r["excess_out"] or 0), cred)}
    results.sort(key=lambda r: (r["status"] != "APPROVED", -(r["t_in"] or -99)))
    approved = [r["id"] for r in results if r["status"] == "APPROVED"]
    return {"asof": max(ds[-1] for ds, _ in data.values()), "symbols": sorted(data), "skipped": skipped,
            "history": {"from": all_dates[0], "to": all_dates[-1], "split": split_date},
            "variants": len(results), "cost_bps_per_side": cost_bps, "fdr": fdr,
            "bonferroni_t": round(M.norm_ppf(1 - 0.05 / len(results)), 3),
            "approved": approved, "results": results}


def report(doc):
    lines = ["# Overnight research: the strategy hunt", "",
             "Data %s to %s, %d symbols. In-sample before %s, out-of-sample after." % (
                 doc["history"]["from"], doc["history"]["to"], len(doc["symbols"]), doc["history"]["split"]),
             "%d rule variants tested. Cost %s bps a side. Benjamini-Hochberg false discovery rate %s; "
             "Bonferroni bar t >= %s." % (doc["variants"], doc["cost_bps_per_side"], doc["fdr"], doc["bonferroni_t"]), ""]
    ap = [r for r in doc["results"] if r["status"] == "APPROVED"]
    lines.append("## Approved: %d" % len(ap))
    if not ap:
        lines.append("None. No rule beat ordinary days by enough, in and out of sample, after costs. "
                     "The bot will not trade until one does. That is the right answer, not a failure.")
    for r in ap:
        lines.append("- **%s**: %s, hold %d days. In-sample %+.2f%% per trade (t %.2f, %d trades), "
                     "out-of-sample %+.2f%% (t %.2f, %d trades), win rate %s.%s" % (
                         r["id"], r["rule"], r["horizon"], 100 * r["excess_in"], r["t_in"], r["events_in"],
                         100 * r["excess_out"], r["t_out"], r["events_out"], M.pct(r["hit_rate"], 0),
                         " Needs short selling." if r["dir"] < 0 else ""))
    lines += ["", "## Closest calls", "", "| rule | status | in-sample excess | t | out-of-sample excess | t |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in doc["results"][:12]:
        f = lambda x: ("%+.2f%%" % (100 * x)) if x is not None else "n/a"
        g = lambda x: ("%.2f" % x) if x is not None else "n/a"
        lines.append("| %s | %s | %s | %s | %s | %s |" % (r["id"], r["status"], f(r["excess_in"]), g(r["t_in"]),
                                                       f(r["excess_out"]), g(r["t_out"])))
    return "\n".join(lines) + "\n"


def today(data_dir=None, asof=None):
    doc = M.load_json(M.path("strategies.json"))
    if not doc:
        raise SystemExit("No mit/strategies.json yet. Run the overnight research first: hunt.py run --write")
    cfg = M.load_config()
    rules = [r for r in doc["results"] if r["status"] == "APPROVED" and (r["dir"] > 0 or cfg.get("allow_short"))]
    cands = []
    for r in rules:
        for s in doc["symbols"]:
            try:
                ds, px = M.closes(M.load_bars(s, data_dir), asof=asof, lookback=400)
            except Exception:
                continue
            if fire_series(px, r["family"], r["params"], {})[-1]:
                cands.append({"symbol": s, "asset_class": M.asset_class(s), "date": ds[-1], "close": px[-1],
                              "setup": {"dip": "dip", "rip": "rip"}.get(r["family"], "trend"),
                              "strategy": r["id"], "rule": r["rule"], "horizon_days": r["horizon"], "edge": r["edge"],
                              "score": r["edge"]["per_trade"]})
    best = {}
    for c in cands:  # one entry per symbol: its strongest firing rule
        if c["symbol"] not in best or c["score"] > best[c["symbol"]]["score"]:
            best[c["symbol"]] = c
    cands = sorted(best.values(), key=lambda c: -c["score"])
    return {"asof": max((c["date"] for c in cands), default=asof), "source": "hunt", "playbook_date": doc["asof"],
            "n_tests": doc["variants"], "candidates": cands, "rules": [r["id"] for r in rules]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tickers"); r.add_argument("--lookback", type=int, default=2520)
    r.add_argument("--cost-bps", type=float, default=10.0); r.add_argument("--fdr", type=float, default=0.10)
    t = sub.add_parser("today")
    sub.add_parser("show")
    for s in (r, t):
        s.add_argument("--data"); s.add_argument("--asof")
        s.add_argument("--write", action="store_true"); s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        cfg = M.load_config()
        if a.tickers:
            tick = a.tickers.split(",")
        elif a.data and os.path.isfile(a.data):
            tick = M.bundle_symbols(a.data)  # a bundled universe: test all of it
        else:
            tick = cfg["universe"]
        doc = run(tick, a.data, a.asof, a.lookback, a.cost_bps, a.fdr)
        text = report(doc)
        if a.write:
            M.save_json(M.path("strategies.json"), doc)
            with open(M.path("research.md"), "w", encoding="utf-8") as fh:
                fh.write(text)
        print(json.dumps(doc, indent=2) if a.json else text)
        if a.write and not a.json:
            print("Wrote %s and %s" % (M.path("strategies.json"), M.path("research.md")))
        return 0
    if a.cmd == "show":
        doc = M.load_json(M.path("strategies.json"))
        if not doc:
            print("No playbook yet. Run: hunt.py run --write")
            return 1
        print(report(doc))
        return 0
    res = today(a.data, a.asof)
    if a.write:
        M.save_json(M.path("candidates.json"), res)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print("Approved rules: %d. Firing on %s: %d" % (len(res["rules"]), res["asof"], len(res["candidates"])))
        for c in res["candidates"]:
            print("  %-8s %-28s %s, hold %d days, edge %+.2f%% a trade" % (
                c["symbol"], c["strategy"], c["rule"], c["horizon_days"], 100 * c["edge"]["per_trade"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
