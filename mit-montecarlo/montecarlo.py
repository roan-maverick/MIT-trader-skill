#!/usr/bin/env python3
"""mit-montecarlo: the odds of a trade plan, from 10,000 simulated futures and from history.

For each plan in mit/plan.json it simulates the next h trading days many
times and counts which comes first: the target, the stop, or neither.

Models (L5, L9, L17, L18, L21):
  garch      (default) GARCH(1,1) variance, with shocks resampled from the
             stock's own standardized past returns: volatility clusters and
             tails are as fat as they really were ("filtered historical simulation")
  gbm        geometric Brownian motion, constant vol, drift 0 by default (Ito: the log
             price drifts by -sigma^2/2 a day)
  bootstrap  past daily returns drawn at random
  ou         for pair plans: the spread is an Ornstein-Uhlenbeck process (an SDE that pulls
             back to its mean)

Between two closes a price can touch the stop and come back. The Brownian
bridge (L17's reflection principle) gives the chance of that, so stops hit
during the day are counted.

It also replays the same rule on the stock's real past: every day the setup
fired, with the stop and target set the same way from the vol of that day.

Usage:
  montecarlo.py run [SYMBOL] [--model garch] [--paths 10000] [--seed 18] [--drift auto|zero|0.001]
                    [--data DIR] [--asof DATE] [--write]

Drift: with no edge, a price is a martingale and Doob's optional stopping theorem (L5)
says a stop and a target change the shape of the outcomes, never their average. So the
drift comes only from /mit-regression's measured edge, shrunk by its credibility.
"""

import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

Z_WINDOW, Z_ENTRY = 20, 2.0


def _std_resid(r, g):
    m = g["mean"]
    vs = g["variances"]
    return [(x - m) / math.sqrt(v) for x, v in zip(r, vs[:-1]) if v > 0]


def drift_for(plan, mode="auto"):
    """Daily log drift for the simulation, and where it came from.

    Without a measured edge the price is a martingale, and Doob's optional stopping
    theorem (L5) says no stop/target rule changes its expected value: E[R] = 0.
    So the only honest source of drift is /mit-regression's event study, shrunk by
    how sure it is: credibility = t / (the bar for luck), between 0 and 1.
    """
    if mode == "zero":
        return 0.0, "zero (no edge assumed)"
    try:
        return float(mode), "given: %s a day" % mode
    except ValueError:
        pass
    sig = (M.load_json(M.path("signals.json")) or {}).get("results", {}).get("%s:%s" % (plan["symbol"], plan["setup"]))
    if not sig or sig["events"]["mean_excess"] is None:
        return 0.0, "zero (no /mit-regression result for this setup)"
    t = sig["events"]["t_excess"] or 0.0
    cred = min(max(t / sig["t_bar"], 0.0), 1.0)
    d = 1 if plan["side"] == "buy" else -1
    mu = d * cred * sig["events"]["mean_excess"] / sig["horizon_days"]
    return mu, "/mit-regression: %+.2f%% excess per %d days x credibility %.2f (t %.2f / bar %.2f)" % (
        100 * sig["events"]["mean_excess"], sig["horizon_days"], cred, t, sig["t_bar"])


def simulate(plan, model="garch", n=10000, seed=M.SEED, data_dir=None, asof=None, lookback=756, drift="auto"):
    rng = random.Random(seed)
    h = int(plan.get("horizon_days", 5))
    if plan.get("pair_with"):
        return simulate_pair(plan, n, rng)
    mu, mu_src = drift_for(plan, drift)
    bars = M.load_bars(plan["symbol"], data_dir)
    _, px = M.closes(bars, asof=asof or plan.get("asof"), lookback=lookback + 1)
    r = M.log_returns(px)
    if model == "garch":
        g = M.garch11(r)
        steps = M.garch_steps(g, _std_resid(r, g), mu)
    elif model == "gbm":
        sd = M.std(r[-252:])
        steps = M.gbm_steps(mu + 0.5 * sd * sd, sd)  # gbm_steps subtracts the Ito term itself
    elif model == "bootstrap":
        rr = r[-504:]
        m = M.mean(rr)
        steps = M.bootstrap_steps([x - m for x in rr], mu)  # de-meaned: no free drift from the past
    else:
        raise ValueError("model must be garch, gbm or bootstrap")
    res = M.first_passage(steps, n, plan["entry"], plan["stop"], plan["target"], h, rng, plan["side"])
    out = summarize(res, plan, model, n, seed)
    out["drift_daily"] = mu
    out["drift_source"] = mu_src
    return out


def simulate_pair(plan, n, rng):
    """OU first passage of the spread (in z units) to the target or the stop."""
    ou = plan["ou"]
    sd = plan["spread_sd"]
    x0, xt, xs = plan["spread_now"], plan["spread_target"], plan["spread_stop"]
    h = int(plan.get("horizon_days", 20))
    sub = 4  # four sub-steps a day keep the barrier check close
    dt = 1.0 / sub
    ht = hs = ne = 0
    pnl = []
    up = xt > x0  # the target is above (spread too low, we bought it)
    for _ in range(n):
        x, out = x0, None
        for _k in range(h * sub):
            x = M.ou_step(x, ou, dt, rng.gauss(0, 1))
            if (up and x >= xt) or (not up and x <= xt):
                out = "t"; break
            if (up and x <= xs) or (not up and x >= xs):
                out = "s"; break
        if out == "t":
            ht += 1; pnl.append(abs(xt - x0) / sd)
        elif out == "s":
            hs += 1; pnl.append(-abs(xs - x0) / sd)
        else:
            ne += 1; pnl.append(((x - x0) if up else (x0 - x)) / sd)
    risk_z = abs(xs - x0) / sd
    rmult = [p / risk_z for p in pnl]
    er = M.mean(rmult)
    se = M.std(rmult) / math.sqrt(n)
    return {"model": "ou", "paths": n, "seed": M.SEED, "p_target": ht / n, "p_stop": hs / n,
            "p_neither": ne / n, "expected_R": er, "expected_R_se": se,
            "kelly_continuous": _kelly_cont(rmult) if er > 2 * se else 0.0,
            "drift_daily": None, "drift_source": "the spread's own pull to its mean (OU fit)"}


def _kelly_cont(rmult):
    """Growth-optimal fraction of capital to risk per trade, f = E[R] / E[R^2] (L16, L25)."""
    m2 = M.mean([x * x for x in rmult])
    return M.mean(rmult) / m2 if m2 > 0 else 0.0


def summarize(res, plan, model, n, seed):
    risk = abs(plan["entry"] - plan["stop"])
    rmult = [p / risk for p in res["pnl"]] if risk > 0 else [0.0]
    ends = sorted(res["ends"])
    er = M.mean(rmult)
    se = M.std(rmult) / math.sqrt(len(rmult)) if len(rmult) > 1 else 0.0
    kelly = _kelly_cont(rmult) if er > 2 * se else 0.0  # an edge inside simulation noise is no edge
    return {"model": model, "paths": n, "seed": seed,
            "p_target": res["target"], "p_stop": res["stop"], "p_neither": res["neither"],
            "expected_R": er, "expected_R_se": se, "expected_pnl_per_unit": M.mean(res["pnl"]),
            "kelly_continuous": kelly,
            "end_price": {"p05": M.quantile(ends, 0.05), "p50": M.quantile(ends, 0.5), "p95": M.quantile(ends, 0.95)}}


def replay(plan, data_dir=None, asof=None, lookback=1260):
    """Every past day the setup fired: did the same stop / target rule win?"""
    if plan.get("pair_with") or plan["setup"] not in ("dip", "rip", "trend"):
        return None
    bars = M.load_bars(plan["symbol"], data_dir)
    dates, px = M.closes(bars, asof=asof or plan.get("asof"), lookback=lookback)
    lp = [math.log(p) for p in px]
    r = M.log_returns(px)
    ew = M.ewma_var(r)  # ew[i] is the variance forecast for r[i] = lp[i+1]-lp[i]
    h = int(plan["horizon_days"])
    ss, ts = plan["stop_sigma"], plan["target_sigma"]
    side = plan["side"]
    wins = losses = neither = 0
    last = -10 ** 9
    events = []
    for i in range(Z_WINDOW - 1, len(px) - h - 1):
        w = lp[i - Z_WINDOW + 1:i + 1]
        sd = M.std(w)
        if sd <= 0:
            continue
        z = (lp[i] - M.mean(w)) / sd
        fire = z <= -Z_ENTRY if plan["setup"] == "dip" else z >= Z_ENTRY if plan["setup"] == "rip" else False
        if plan["setup"] == "trend":
            continue  # the trend rule needs the 63-day regression; the simulation covers it
        if not fire or i - last < h:
            continue
        last = i
        sig_h = math.sqrt(ew[i] * h)
        e = px[i]
        if side == "buy":
            stop, tgt = e * math.exp(-ss * sig_h), e * math.exp(ts * sig_h)
        else:
            stop, tgt = e * math.exp(ss * sig_h), e * math.exp(-ts * sig_h)
        out = "neither"
        for k in range(1, h + 1):
            p = px[i + k]
            if (side == "buy" and p <= stop) or (side == "sell" and p >= stop):
                out = "stop"; break
            if (side == "buy" and p >= tgt) or (side == "sell" and p <= tgt):
                out = "target"; break
        events.append({"date": dates[i], "outcome": out})
        if out == "target":
            wins += 1
        elif out == "stop":
            losses += 1
        else:
            neither += 1
    return {"fired": len(events), "target": wins, "stop": losses, "neither": neither,
            "from": dates[0], "to": dates[-1], "last_events": events[-8:],
            "note": "closes only: a stop touched during the day and recovered by the close counts as not hit"}


def verdict(sim):
    er, se = sim["expected_R"], sim.get("expected_R_se", 0.0)
    if er > max(0.1, 2 * se):
        return "the odds lean your way"
    if er < -max(0.05, 2 * se):
        return "the odds lean against you"
    return "close to a coin flip"


def show(plan, sim, rep):
    print("%s %s %s: entry %s, stop %s, target %s, %d days" % (
        plan["side"], plan["symbol"] + (" vs " + plan["pair_with"] if plan.get("pair_with") else ""),
        plan["setup"], M.num(plan.get("entry")), M.num(plan.get("stop")), M.num(plan.get("target")), plan["horizon_days"]))
    print("  %s paths (%s model, seed %s): target first %s, stop first %s, neither by day %d %s" % (
        "{:,}".format(sim["paths"]), sim["model"], sim["seed"], M.pct(sim["p_target"]), M.pct(sim["p_stop"]),
        plan["horizon_days"], M.pct(sim["p_neither"])))
    print("  drift: %s" % sim.get("drift_source"))
    print("  expected result %+.3f R (+/- %.3f; R = the amount at risk); growth-optimal Kelly risk fraction %s" % (
        sim["expected_R"], 2 * sim.get("expected_R_se", 0), M.pct(max(sim["kelly_continuous"], 0), 1)))
    if sim.get("end_price"):
        ep = sim["end_price"]
        print("  price in %d days: 5%% chance below %s, median %s, 5%% chance above %s" % (
            plan["horizon_days"], M.num(ep["p05"]), M.num(ep["p50"]), M.num(ep["p95"])))
    if rep:
        print("  history %s to %s: the rule fired %d times; %d hit the target, %d the stop, %d neither" % (
            rep["from"], rep["to"], rep["fired"], rep["target"], rep["stop"], rep["neither"]))
    print("  verdict: %s." % verdict(sim))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("symbol", nargs="?")
    r.add_argument("--model", default="garch", choices=["garch", "gbm", "bootstrap"])
    r.add_argument("--paths", type=int, default=10000)
    r.add_argument("--seed", type=int, default=M.SEED)
    r.add_argument("--drift", default="auto", help="auto (from /mit-regression), zero, or a daily log drift like 0.001")
    r.add_argument("--data")
    r.add_argument("--asof")
    r.add_argument("--write", action="store_true")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pth = M.path("plan.json")
    doc = M.load_json(pth)
    if not doc or not doc.get("plans"):
        print("No mit/plan.json yet. Run /mit-volatility plan (or /mit-pairs plan) first.")
        return 1
    plans = [p for p in doc["plans"] if not a.symbol or p["symbol"] == M.norm_symbol(a.symbol)]
    out = []
    for p in plans:
        sim = simulate(p, a.model, a.paths, a.seed, a.data, a.asof, drift=a.drift)
        rep = replay(p, a.data, a.asof)
        p["montecarlo"] = sim
        p["history"] = rep
        p["odds_verdict"] = verdict(sim)
        out.append(p)
        if not a.json:
            show(p, sim, rep)
    if a.write:
        M.save_json(pth, doc)
        if not a.json:
            print("Wrote the odds into %s" % pth)
    if a.json:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
