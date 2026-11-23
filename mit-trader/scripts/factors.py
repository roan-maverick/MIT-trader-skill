#!/usr/bin/env python3
# Reviewed for local use
"""mit-trader / factors: how much of a stock's move is just the market, and is any alpha left?

  beta   CAPM regression on a benchmark (L1, L6, Case Study 1): alpha, beta, R^2,
         plus a Kalman-filter beta that changes over time (L12: time-varying CAPM)
  model  a macro factor model from ETFs (L15): market, small caps, tech, long bonds,
         gold, energy. Loadings, R^2 and the alpha left over.
  pca    principal components of a universe's returns (L2, L15): how many hidden
         factors really drive it, and which stocks load on them

Usage:
  factors.py beta NVDA [--bench SPY] [--window 252] [--data DIR] [--asof DATE] [--write]
  factors.py model NVDA [--window 252] [--data DIR] [--asof DATE] [--write]
  factors.py pca [--tickers A,B,C] [--window 252] [--data DIR] [--asof DATE]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

FACTORS = [  # name, long leg, short leg (None: just the ETF)
    ("market", "SPY", None), ("small_caps", "IWM", "SPY"), ("tech", "QQQ", "SPY"),
    ("long_bonds", "TLT", None), ("gold", "GLD", None), ("energy", "XLE", None),
]


def returns(syms, data_dir, asof, window):
    series = {}
    for s in syms:
        d, c = M.closes(M.load_bars(s, data_dir), asof=asof, lookback=window + 40)
        r = M.log_returns(c)
        series[M.norm_symbol(s)] = (d[1:], r)
    dates, aligned = M.align(series)
    dates = dates[-window:]
    return dates, {k: v[-window:] for k, v in aligned.items()}


def beta(sym, bench="SPY", data_dir=None, asof=None, window=252):
    sym, bench = M.norm_symbol(sym), M.norm_symbol(bench)
    dates, R = returns([sym, bench], data_dir, asof, window)
    y, x = R[sym], R[bench]
    fit = M.ols(y, x)
    a, b = fit["beta"]
    ann = 252
    kal = M.kalman_beta(y, x, delta=1e-4)
    idio = fit["sigma"] * math.sqrt(ann)
    return {"symbol": sym, "benchmark": bench, "asof": dates[-1], "days": len(y),
            "beta": b, "beta_t": fit["t"][1], "alpha_daily": a, "alpha_ann": a * ann, "alpha_t": fit["t"][0],
            "alpha_p": fit["p"][0], "r2": fit["r2"], "idio_vol_ann": idio, "total_vol_ann": M.std(y) * math.sqrt(ann),
            "beta_kalman_now": kal["beta"][-1], "beta_kalman_60d_ago": kal["beta"][-61] if len(y) > 61 else None,
            "corr": M.corr(y, x)}


def model(sym, data_dir=None, asof=None, window=252):
    sym = M.norm_symbol(sym)
    need = {sym} | {f[1] for f in FACTORS} | {f[2] for f in FACTORS if f[2]}
    dates, R = returns(sorted(need), data_dir, asof, window)
    X, names = [], [f[0] for f in FACTORS]
    for t in range(len(dates)):
        X.append([R[l][t] - (R[s][t] if s else 0.0) for _, l, s in FACTORS])
    fit = M.ols(R[sym], X)
    load = {names[i]: {"loading": fit["beta"][i + 1], "t": fit["t"][i + 1]} for i in range(len(names))}
    return {"symbol": sym, "asof": dates[-1], "days": len(dates), "factors": load,
            "alpha_ann": fit["beta"][0] * 252, "alpha_t": fit["t"][0], "r2": fit["r2"],
            "idio_vol_ann": fit["sigma"] * math.sqrt(252),
            "definitions": {n: (l + (" minus " + s if s else "")) for n, l, s in FACTORS}}


def pca(tickers, data_dir=None, asof=None, window=252):
    tick = []
    for t in tickers:
        try:
            M.load_bars(t, data_dir)
            tick.append(M.norm_symbol(t))
        except Exception:
            pass
    dates, R = returns(tick, data_dir, asof, window)
    # standardize: PCA of the correlation matrix, so a wild stock does not dominate
    Z = []
    sd = {k: M.std(v) for k, v in R.items()}
    mu = {k: M.mean(v) for k, v in R.items()}
    for t in range(len(dates)):
        Z.append([(R[k][t] - mu[k]) / sd[k] for k in tick])
    C = M.cov_matrix(Z)
    vals, vecs = M.eig_sym(C)
    tot = sum(vals)
    comps = []
    for i in range(min(3, len(vals))):
        load = sorted(zip(tick, vecs[i]), key=lambda x: -abs(x[1]))
        comps.append({"pc": i + 1, "share_of_variance": vals[i] / tot, "eigenvalue": vals[i],
                      "top_loadings": [(s, round(v, 3)) for s, v in load[:8]]})
    # how many PCs a random (no-structure) matrix of this shape would explain: Marchenko-Pastur edge
    q = len(tick) / float(len(dates))
    mp_edge = (1 + math.sqrt(q)) ** 2
    return {"asof": dates[-1], "days": len(dates), "symbols": tick, "components": comps,
            "eigenvalues": [round(v, 3) for v in vals],
            "signal_factors": sum(1 for v in vals if v > mp_edge), "noise_edge": mp_edge}


def save(key, obj):
    p = M.path("factors.json")
    doc = M.load_json(p, {}) or {}
    doc.setdefault(obj["symbol"], {})[key] = obj
    M.save_json(p, doc)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("beta"); b.add_argument("symbol"); b.add_argument("--bench", default="SPY")
    m = sub.add_parser("model"); m.add_argument("symbol")
    p = sub.add_parser("pca"); p.add_argument("--tickers")
    for s in (b, m, p):
        s.add_argument("--window", type=int, default=252)
        s.add_argument("--data"); s.add_argument("--asof"); s.add_argument("--config")
        s.add_argument("--json", action="store_true"); s.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "beta":
        r = beta(a.symbol, a.bench, a.data, a.asof, a.window)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print("%s vs %s, %d daily returns to %s" % (r["symbol"], r["benchmark"], r["days"], r["asof"]))
            print("  beta %.2f (t %.1f): a 1%% move in %s comes with %.2f%% in %s on average" % (
                r["beta"], r["beta_t"], r["benchmark"], r["beta"], r["symbol"]))
            print("  Kalman beta now %.2f (60 days ago %s)" % (r["beta_kalman_now"], M.num(r["beta_kalman_60d_ago"])))
            print("  R^2 %s: that share of its daily variance is the market; the rest is its own" % M.pct(r["r2"], 0))
            print("  alpha %s a year, t = %.2f, p = %.2f: %s" % (
                M.pct(r["alpha_ann"]), r["alpha_t"], r["alpha_p"],
                "statistically real" if abs(r["alpha_t"]) >= 2 else "not distinguishable from zero"))
            print("  vol %s a year, of which stock-specific %s" % (M.pct(r["total_vol_ann"], 0), M.pct(r["idio_vol_ann"], 0)))
    elif a.cmd == "model":
        r = model(a.symbol, a.data, a.asof, a.window)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print("%s factor model, %d days to %s (R^2 %s)" % (r["symbol"], r["days"], r["asof"], M.pct(r["r2"], 0)))
            for k, v in r["factors"].items():
                print("  %-11s %-16s loading %+.2f  t %+.1f" % (k, r["definitions"][k], v["loading"], v["t"]))
            print("  alpha %s a year, t = %.2f" % (M.pct(r["alpha_ann"]), r["alpha_t"]))
    else:
        cfg = M.load_config(a.config)
        tick = a.tickers.split(",") if a.tickers else [t for t in cfg["universe"] if not M.is_crypto(t)]
        r = pca(tick, a.data, a.asof, a.window)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print("PCA of %d symbols, %d days to %s" % (len(r["symbols"]), r["days"], r["asof"]))
            for c in r["components"]:
                print("  PC%d explains %s: %s" % (c["pc"], M.pct(c["share_of_variance"]),
                      ", ".join("%s %+.2f" % x for x in c["top_loadings"])))
            print("  eigenvalues above the random-noise edge (%.2f): %d real factors" % (r["noise_edge"], r["signal_factors"]))
        return 0
    if a.write:
        print("Wrote %s" % save(a.cmd, r)) if not a.json else save(a.cmd, r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
