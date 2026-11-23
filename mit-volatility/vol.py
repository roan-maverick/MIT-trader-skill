#!/usr/bin/env python3
"""mit-volatility: forecast volatility with GARCH(1,1) and set stops and targets from it.

L9 (Volatility Modeling): daily returns are not constant-variance. Big moves
cluster. GARCH(1,1) fitted by maximum likelihood says how wild the next few
days are likely to be, and that sets how far away a stop must sit so normal
noise does not hit it.

Usage:
  vol.py fit NVDA [--data DIR] [--asof DATE] [--json]
  vol.py plan NVDA [--setup dip] [--entry 125.53] [--stop-sigma 1] [--target-sigma 2]
                   [--target mean] [--horizon 5] [--write]
  vol.py plan --from-candidates [--only-edge] [--top 3] [--write]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

LONG_SETUPS = ("dip", "trend", "manual-long")


def fit(sym, data_dir=None, asof=None, lookback=756, horizon=5):
    bars = M.load_bars(sym, data_dir)
    dates, px = M.closes(bars, asof=asof, lookback=lookback + 1)
    r = M.log_returns(px)
    ann = 365 if M.is_crypto(sym) else 252
    g = M.garch11(r)
    fc = M.garch_forecast(g, horizon)
    ew = M.ewma_var(r)[-1]
    lb_q, lb_p = M.ljung_box([x * x for x in r], 10)
    sig_h = math.sqrt(sum(fc))
    return {
        "symbol": M.norm_symbol(sym), "asof": dates[-1], "close": px[-1], "days": len(r),
        "annualize": ann,
        "garch": {"omega": g["omega"], "alpha": round(g["alpha"], 4), "beta": round(g["beta"], 4),
                  "persistence": round(g["persistence"], 4), "half_life_days": round(g["half_life"], 1)},
        "vol_next_day": math.sqrt(g["var_next"]), "vol_next_day_ann": math.sqrt(g["var_next"] * ann),
        "vol_long_run_ann": math.sqrt(g["long_run_var"] * ann) if g["long_run_var"] != float("inf") else None,
        "vol_ewma_ann": math.sqrt(ew * ann), "vol_20d_ann": M.std(r[-20:]) * math.sqrt(ann),
        "horizon_days": horizon, "vol_horizon": sig_h,
        "fat_tails": {"excess_kurtosis": round(M.kurtosis(r), 2), "skew": round(M.skew(r), 2)},
        "arch_effect": {"ljung_box_q_sq_returns": round(lb_q, 1), "p": lb_p},
        "_g": g,
    }


def make_plan(f, setup="dip", entry=None, stop_sigma=1.0, target_sigma=2.0, target_mode="sigma",
              mean20=None, horizon=5):
    side = "buy" if setup in LONG_SETUPS else "sell"
    e = float(entry or f["close"])
    s = f["vol_horizon"]
    if side == "buy":
        stop = e * math.exp(-stop_sigma * s)
        target = e * math.exp(target_sigma * s)
        if target_mode == "mean" and mean20 and mean20 > e:
            target = mean20
    else:
        stop = e * math.exp(stop_sigma * s)
        target = e * math.exp(-target_sigma * s)
        if target_mode == "mean" and mean20 and mean20 < e:
            target = mean20
    rnd = (lambda x: round(x, 2)) if e >= 1 else (lambda x: round(x, 6))  # broker prices: cents
    e, stop, target = rnd(e), rnd(stop), rnd(target)
    risk = abs(e - stop)
    reward = abs(target - e)
    return {
        "symbol": f["symbol"], "asset_class": M.asset_class(f["symbol"]), "setup": setup, "side": side,
        "asof": f["asof"], "entry": round(e, 4), "stop": round(stop, 4), "target": round(target, 4),
        "risk_per_unit": round(risk, 4), "reward_per_unit": round(reward, 4),
        "reward_risk": round(reward / risk, 3) if risk > 0 else None,
        "horizon_days": horizon, "stop_sigma": stop_sigma, "target_sigma": target_sigma,
        "target_mode": target_mode, "vol_horizon": round(s, 5),
        "vol_next_day_ann": round(f["vol_next_day_ann"], 4),
        "garch": f["garch"], "model": "GARCH(1,1), Gaussian MLE",
    }


def show_fit(f):
    g = f["garch"]
    print("%s volatility, %d daily returns to %s" % (f["symbol"], f["days"], f["asof"]))
    print("  GARCH(1,1): alpha %.3f (reaction to news), beta %.3f (memory), persistence %.3f, "
          "a shock halves in %s days" % (g["alpha"], g["beta"], g["persistence"], g["half_life_days"]))
    print("  annualized vol: tomorrow %s, long-run %s, EWMA %s, last 20 days %s" % (
        M.pct(f["vol_next_day_ann"]), M.pct(f["vol_long_run_ann"]), M.pct(f["vol_ewma_ann"]), M.pct(f["vol_20d_ann"])))
    print("  next %d days: one standard deviation is %s (move of %s on %s)" % (
        f["horizon_days"], M.pct(f["vol_horizon"], 2), M.money(f["close"] * f["vol_horizon"]), M.num(f["close"])))
    ft = f["fat_tails"]
    print("  fat tails: excess kurtosis %s (normal = 0), skew %s" % (ft["excess_kurtosis"], ft["skew"]))
    ae = f["arch_effect"]
    print("  volatility clustering: Ljung-Box on squared returns Q = %s, p = %s%s" % (
        ae["ljung_box_q_sq_returns"], M.num(ae["p"], 4),
        " (strong: big days follow big days)" if ae["p"] < 0.01 else ""))


def show_plan(p):
    word = "buy" if p["side"] == "buy" else "sell short"
    print("Plan: %s %s at %s (%s setup, %d-day horizon)" % (word, p["symbol"], M.num(p["entry"]), p["setup"], p["horizon_days"]))
    print("  stop   %s  (%s sigma of the %d-day GARCH vol %s: %s a unit at risk)" % (
        M.num(p["stop"]), p["stop_sigma"], p["horizon_days"], M.pct(p["vol_horizon"], 2), M.num(p["risk_per_unit"])))
    tgt = "the 20-day mean" if p["target_mode"] == "mean" else "%s sigma" % p["target_sigma"]
    print("  target %s  (%s: %s a unit)  reward:risk %s" % (M.num(p["target"]), tgt, M.num(p["reward_per_unit"]), M.num(p["reward_risk"])))


def save_plans(plans):
    pth = M.path("plan.json")
    doc = M.load_json(pth, {}) or {}
    have = {(x["symbol"], x.get("pair_with")): x for x in doc.get("plans", [])}
    for p in plans:
        have[(p["symbol"], p.get("pair_with"))] = p
    doc["plans"] = list(have.values())
    doc["asof"] = max(p["asof"] for p in doc["plans"])
    M.save_json(pth, doc)
    return pth


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("symbol")
    p = sub.add_parser("plan")
    p.add_argument("symbol", nargs="?")
    p.add_argument("--setup", default="dip", choices=["dip", "trend", "rip", "slide", "manual-long", "manual-short"])
    p.add_argument("--entry", type=float)
    p.add_argument("--stop-sigma", type=float)
    p.add_argument("--target-sigma", type=float)
    p.add_argument("--target", choices=["sigma", "mean"], default="sigma")
    p.add_argument("--from-candidates", action="store_true")
    p.add_argument("--only-edge", action="store_true", help="only candidates /mit-regression rated EDGE")
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--write", action="store_true")
    p.add_argument("--replace", action="store_true", help="start plan.json fresh instead of merging")
    for s in (f, p):
        s.add_argument("--horizon", type=int)
        s.add_argument("--data")
        s.add_argument("--asof")
        s.add_argument("--config")
        s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = M.load_config(a.config)
    h = a.horizon or int(cfg["horizon_days"])
    if a.cmd == "fit":
        res = fit(a.symbol, a.data, a.asof, horizon=h)
        res.pop("_g")
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            show_fit(res)
        return 0
    ss = a.stop_sigma if a.stop_sigma is not None else float(cfg["stop_sigma"])
    ts = a.target_sigma if a.target_sigma is not None else float(cfg["target_sigma"])
    jobs = []
    if a.from_candidates:
        cands = (M.load_json(M.path("candidates.json")) or {}).get("candidates", [])
        sigs = (M.load_json(M.path("signals.json")) or {}).get("results", {})
        for c in cands:
            if c["setup"] == "slide":
                continue  # a falling trend is a warning, not a trade
            if c["setup"] == "rip" and not cfg.get("allow_short"):
                continue
            v = sigs.get("%s:%s" % (c["symbol"], c["setup"]), {}).get("verdict")
            if a.only_edge and v != "EDGE":
                continue
            jobs.append((c["symbol"], c["setup"], None, c.get("mean20")))
        rank = {"EDGE": 0, "WEAK": 1}
        jobs.sort(key=lambda j: rank.get(sigs.get("%s:%s" % (j[0], j[1]), {}).get("verdict"), 2))  # stable: keeps score order
        jobs = jobs[:a.top]
        if not jobs:
            print("No candidates to plan." + (" None was rated EDGE." if a.only_edge else ""))
            return 0
    else:
        if not a.symbol:
            ap.error("give a symbol or --from-candidates")
        mean20 = None
        if a.target == "mean":
            bars = M.load_bars(a.symbol, a.data)
            _, px = M.closes(bars, asof=a.asof, lookback=20)
            mean20 = math.exp(M.mean([math.log(x) for x in px]))
        jobs.append((a.symbol, a.setup, a.entry, mean20))
    plans = []
    for sym, setup, entry, mean20 in jobs:
        fr = fit(sym, a.data, a.asof, horizon=h)
        plans.append(make_plan(fr, setup, entry, ss, ts, a.target, mean20, h))
    if a.write:
        if a.replace:
            M.save_json(M.path("plan.json"), {"plans": []})
        where = save_plans(plans)
    if a.json:
        print(json.dumps(plans if len(plans) > 1 else plans[0], indent=2))
    else:
        for pl in plans:
            show_plan(pl)
        if a.write:
            print("Wrote %s" % where)
    return 0


if __name__ == "__main__":
    sys.exit(main())
