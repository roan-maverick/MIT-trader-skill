#!/usr/bin/env python3
"""mit-options: price options, read their Greeks, and turn option prices into probabilities.

  price     Black-Scholes price and Greeks (L19; Ito's lemma, L18, gives the PDE)
  iv        the volatility a market price implies
  prob      the risk-neutral chance of finishing above / below a price, N(d2), and
            the digital option that pays $1 if it does (L20: option prices ARE probabilities)
  chain     a whole strike chain -> the market's implied probability distribution
            (Breeden-Litzenberger: the second derivative of call prices in the strike, L20, L25),
            its expected move and its fat tails, next to the lognormal guess
  move      the expected move priced by the at-the-money straddle

Rates and dividend yields are continuous, per year. T is in years (30 days = 30/365).
Chain files are CSV with columns strike,call (mid prices) or strike,bid,ask. Copy them from
your broker; this tool does not download chains.

Usage:
  options.py price --spot 125.53 --strike 130 --days 30 --vol 0.65 [--rate 0.04] [--put]
  options.py iv --price 9.10 --spot 125.53 --strike 130 --days 30 [--put]
  options.py prob --spot 125.53 --level 150 --days 30 --vol 0.65
  options.py chain --file nvda_dec.csv --spot 125.53 --days 30 [--rate 0.04]
  options.py move --spot 125.53 --call 9.10 --put 8.70
"""

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402


def read_chain(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r = {k.strip().lower(): v for k, v in r.items()}
            k = float(r["strike"])
            if r.get("call"):
                c = float(r["call"])
            else:
                c = (float(r["bid"]) + float(r["ask"])) / 2
            rows.append((k, c))
    rows.sort()
    return rows


def implied_distribution(chain, spot, T, r):
    """Breeden-Litzenberger: density f(K) = e^{rT} d2C/dK2; P(S_T > K) = -e^{rT} dC/dK."""
    ks = [k for k, _ in chain]
    cs = [c for _, c in chain]
    g = math.exp(r * T)
    dens, tail = [], []
    for i in range(1, len(ks) - 1):
        h1, h2 = ks[i] - ks[i - 1], ks[i + 1] - ks[i]
        d2 = 2 * (cs[i + 1] * h1 - cs[i] * (h1 + h2) + cs[i - 1] * h2) / (h1 * h2 * (h1 + h2))
        dens.append((ks[i], max(g * d2, 0.0)))
    for i in range(len(ks) - 1):
        slope = (cs[i + 1] - cs[i]) / (ks[i + 1] - ks[i])
        tail.append(((ks[i] + ks[i + 1]) / 2, min(max(-g * slope, 0.0), 1.0)))
    # mass, mean and spread of the density on the grid
    mass = sum(dens[i][1] * ((dens[i + 1][0] - dens[i - 1][0]) / 2) for i in range(1, len(dens) - 1))
    mean = sum(dens[i][0] * dens[i][1] * ((dens[i + 1][0] - dens[i - 1][0]) / 2) for i in range(1, len(dens) - 1))
    mean = mean / mass if mass > 0 else float("nan")
    return {"density": dens, "prob_above": tail, "mass_captured": mass, "mean": mean}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("price"); iv = sub.add_parser("iv"); pb = sub.add_parser("prob")
    ch = sub.add_parser("chain"); mv = sub.add_parser("move")
    for s in (pr, iv, pb, ch):
        s.add_argument("--spot", type=float, required=True)
        s.add_argument("--days", type=float, required=True)
        s.add_argument("--rate", type=float, default=0.04)
        s.add_argument("--div", type=float, default=0.0)
    for s in (pr, iv):
        s.add_argument("--strike", type=float, required=True)
        s.add_argument("--put", action="store_true")
    pr.add_argument("--vol", type=float, required=True)
    iv.add_argument("--price", type=float, required=True)
    pb.add_argument("--level", type=float, required=True); pb.add_argument("--vol", type=float, required=True)
    ch.add_argument("--file", required=True)
    mv.add_argument("--spot", type=float, required=True); mv.add_argument("--call", type=float, required=True)
    mv.add_argument("--put", type=float, required=True)
    for s in (pr, iv, pb, ch, mv):
        s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = {}
    if a.cmd == "price":
        T = a.days / 365.0
        kind = "put" if a.put else "call"
        g = M.bs(a.spot, a.strike, T, a.rate, a.vol, kind, a.div)
        out = dict(g, kind=kind)
        if not a.json:
            print("%s %s strike, %g days, vol %s: price %s" % (kind, M.num(a.strike), a.days, M.pct(a.vol), M.num(g["price"], 3)))
            print("  delta %.3f (shares to hedge one option), gamma %.4f, vega %.3f per vol point, theta %.3f a day" % (
                g["delta"], g["gamma"], g["vega"], g["theta"]))
            print("  risk-neutral chance it finishes in the money: %s" % M.pct(g["prob_itm"]))
    elif a.cmd == "iv":
        T = a.days / 365.0
        kind = "put" if a.put else "call"
        v = M.implied_vol(a.price, a.spot, a.strike, T, a.rate, kind, a.div)
        out = {"implied_vol": v}
        if not a.json:
            print("implied vol %s (a %s at %s with %g days left)" % (M.pct(v), kind, M.num(a.price), a.days))
    elif a.cmd == "prob":
        T = a.days / 365.0
        d2 = M.bs(a.spot, a.level, T, a.rate, a.vol, "call", a.div)["d2"]
        p_above = M.norm_cdf(d2)
        dig = math.exp(-a.rate * T) * p_above
        out = {"prob_above": p_above, "prob_below": 1 - p_above, "digital_call": dig}
        if not a.json:
            print("risk-neutral odds in %g days at vol %s: above %s %s, below %s" % (
                a.days, M.pct(a.vol), M.num(a.level), M.pct(p_above), M.pct(1 - p_above)))
            print("  a digital option paying $1 above %s is worth %s today. Risk-neutral odds price risk; "
                  "they are not a forecast (L25)." % (M.num(a.level), M.num(dig, 4)))
    elif a.cmd == "chain":
        T = a.days / 365.0
        chain = read_chain(a.file)
        d = implied_distribution(chain, a.spot, T, a.rate)
        atm = min(chain, key=lambda x: abs(x[0] - a.spot))
        atm_iv = M.implied_vol(atm[1], a.spot, atm[0], T, a.rate)
        out = {"atm_iv": atm_iv, **{k: v for k, v in d.items()}}
        if not a.json:
            print("Implied distribution from %d strikes, %g days, spot %s (ATM implied vol %s)" % (
                len(chain), a.days, M.num(a.spot), M.pct(atm_iv)))
            print("  captured probability %s, implied mean %s (forward %s)" % (
                M.pct(d["mass_captured"]), M.num(d["mean"]), M.num(a.spot * math.exp((a.rate - a.div) * T))))
            print("  strike     P(above), market   P(above), lognormal at ATM vol")
            for k, p in d["prob_above"][::max(1, len(d["prob_above"]) // 12)]:
                ln = M.norm_cdf(M.bs(a.spot, k, T, a.rate, atm_iv)["d2"])
                print("  %-9s  %-18s %s" % (M.num(k), M.pct(p), M.pct(ln)))
            print("  Where the market's odds of a crash beat the lognormal's, it prices a fatter left tail (the skew).")
    else:
        straddle = a.call + a.put
        sd = straddle / math.sqrt(2 / math.pi)
        out = {"straddle": straddle, "expected_abs_move": straddle, "one_sd_move": sd, "one_sd_pct": sd / a.spot}
        if not a.json:
            print("ATM straddle %s: the market expects an average move of about %s (%s) by expiry;" % (
                M.num(straddle), M.num(straddle), M.pct(straddle / a.spot)))
            print("  one standard deviation is about %s (%s): straddle / 0.8, since E|Z| = sqrt(2/pi) ~ 0.8" % (
                M.num(sd), M.pct(sd / a.spot)))
    if a.json:
        print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
