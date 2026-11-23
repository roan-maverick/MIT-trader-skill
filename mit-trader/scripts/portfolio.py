#!/usr/bin/env python3
"""mit-trader / portfolio: how much to buy (Kelly sizing) and how to split money across assets.

  size      turns each plan in mit/plan.json into an order in mit/orders.json.
            Kelly (L16, L25): risk the fraction of capital that maximizes long-run
            growth, f = E[R] / E[R^2] from the Monte Carlo outcomes, times your
            kelly_fraction (half Kelly by default). Then your hard limits cap it:
            max loss per trade, position size, cash. Kelly at or below zero means
            the odds do not pay: no order.
            --method fixed ignores Kelly and risks exactly your max loss per trade.
  optimize  long-term allocation across assets (L14 Markowitz, L16 risk parity), on a
            Ledoit-Wolf shrinkage covariance (L10: regularize a noisy estimate),
            with a cap per asset (Case Study 6 caps at 30%). Writes mit/targets.json.

Usage:
  portfolio.py size [--method kelly|fixed] [--write]
  portfolio.py optimize --tickers SPY,TLT,GLD,QQQ [--method riskparity|minvar|meanvar] [--cap 0.30]
                        [--window 504] [--data DIR] [--asof DATE] [--write]
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402


def equity_and_cash(cfg):
    pf = M.load_json(M.path("portfolio.json"))
    if not pf:
        b = float(cfg["budget"])
        return b, b, {}, "a fresh account funded with your budget (%s)" % M.money(b)
    cash = float(pf.get("cash", 0))
    pos = {M.norm_symbol(p["symbol"]): p for p in pf.get("positions", [])}
    val = sum(float(p.get("qty", 0)) * float(p.get("price", p.get("avg_price", 0))) for p in pos.values())
    return cash + val, cash, pos, "mit/portfolio.json"


def size_plan(plan, cfg, equity, cash, method="kelly"):
    risk_u = abs(plan["entry"] - plan["stop"])
    mc = plan.get("montecarlo") or {}
    k_full = mc.get("kelly_continuous")
    kf = float(cfg["kelly_fraction"])
    notes = []
    if method == "kelly":
        if k_full is None:
            return None, ["no Monte Carlo odds in the plan: run the Monte Carlo first, or use --method fixed"]
        f = max(k_full, 0.0) * kf
        risk_budget = f * equity
        notes.append("Kelly: full %s of capital at risk, x %s = %s (%s)" % (
            M.pct(max(k_full, 0), 2), kf, M.pct(f, 2), M.money(risk_budget)))
        if f <= 0:
            return None, notes + ["Kelly says do not bet: the simulated odds do not pay for the risk"]
    else:
        risk_budget = float(cfg["max_loss_per_trade_usd"])
        notes.append("fixed: risk your max loss per trade, %s" % M.money(risk_budget))
    cap_loss = float(cfg["max_loss_per_trade_usd"])
    if risk_budget > cap_loss:
        notes.append("capped at your max loss per trade, %s" % M.money(cap_loss))
        risk_budget = cap_loss
    crypto = plan.get("asset_class") == "crypto"
    frac = crypto or cfg.get("fractional")
    qty = risk_budget / risk_u if risk_u > 0 else 0
    limits = [
        (float(cfg["max_position_pct"]) / 100 * equity / plan["entry"], "max position %s%% of %s" % (cfg["max_position_pct"], M.money(equity))),
        (float(cfg["max_order_usd"]) / plan["entry"], "max order %s" % M.money(cfg["max_order_usd"])),
        (max(cash - float(cfg["cash_buffer_pct"]) / 100 * equity, 0) / plan["entry"], "cash after the %s%% buffer" % cfg["cash_buffer_pct"]),
    ]
    for lim, why in limits:
        if qty > lim:
            qty = lim
            notes.append("capped by " + why)
    qty = math.floor(qty * 1e6) / 1e6 if frac else math.floor(qty)
    if qty <= 0:
        return None, notes + ["0 units fit the limits"]
    return qty, notes


def build_order(plan, qty, idx):
    crypto = plan.get("asset_class") == "crypto"
    q = ("%.6f" % qty).rstrip("0").rstrip(".") if crypto or qty != int(qty) else str(int(qty))
    o = {"id": "o%d" % idx, "symbol": M.broker_symbol(plan["symbol"]), "asset_class": plan.get("asset_class", "us_equity"),
         "side": plan["side"], "qty": q, "type": "market"}
    if crypto:
        o["time_in_force"] = "gtc"  # Alpaca crypto: no bracket orders; the stop lives in the plan
    else:
        o["time_in_force"] = "gtc"
        o["order_class"] = "bracket"
        o["take_profit_limit_price"] = M.price_str(plan["target"])
        o["stop_loss_stop_price"] = M.price_str(plan["stop"])
    o["plan"] = {"entry": plan["entry"], "stop": plan["stop"], "target": plan["target"], "setup": plan["setup"],
                 "horizon_days": plan["horizon_days"], "asof": plan["asof"]}
    if plan.get("strategy"):
        o["plan"]["strategy"] = plan["strategy"]
    return o


def cmd_size(a, cfg):
    doc = M.load_json(M.path("plan.json"))
    if not doc or not doc.get("plans"):
        print("No mit/plan.json. Run vol.py plan and montecarlo.py run first.")
        return 1
    equity, cash, _, src = equity_and_cash(cfg)
    orders, report = [], []
    for p in doc["plans"]:
        if p.get("pair_with"):
            qty, notes = size_pair(p, cfg, equity, cash, a.method)
            if qty:
                legs = pair_orders(p, qty, len(orders) + 1)
                if int(legs[0]["qty"]) < 1 or int(legs[1]["qty"]) < 1:
                    qty, notes = None, notes + ["under one share on a leg"]
                else:
                    orders.extend(legs)
                    notes.append("legs: %s %s %s (%s), %s %s %s (%s); max loss at the spread stop %s" % (
                        legs[0]["side"], legs[0]["qty"], legs[0]["symbol"], M.money(int(legs[0]["qty"]) * p["price_a"]),
                        legs[1]["side"], legs[1]["qty"], legs[1]["symbol"], M.money(int(legs[1]["qty"]) * p["price_b"]),
                        M.money(legs[0]["plan"]["pair_max_loss"])))
            report.append((p, qty, notes))
            continue
        qty, notes = size_plan(p, cfg, equity, cash, a.method)
        if qty:
            o = build_order(p, qty, len(orders) + 1)
            orders.append(o)
            cash -= qty * p["entry"] if p["side"] == "buy" else 0
        report.append((p, qty, notes))
    out = {"asof": doc.get("asof"), "method": a.method, "equity": equity, "account": src, "orders": orders}
    if a.json:
        print(json.dumps({"report": [{"symbol": p["symbol"], "qty": q, "notes": n} for p, q, n in report], **out}, indent=2))
    else:
        print("Account: %s, equity %s" % (src, M.money(equity)))
        for p, q, notes in report:
            name = p["symbol"] + (" / " + p["pair_with"] if p.get("pair_with") else "")
            if q and p.get("pair_with"):
                print("  %s: pair trade, hedge ratio %.2f" % (name, p["hedge_ratio"]))
            elif q:
                risk = q * abs(p["entry"] - p["stop"])
                print("  %s: %s %s units at %s = %s; max loss at the stop %s" % (
                    name, p["side"], M.num(q, 6 if p.get("asset_class") == "crypto" else 0), M.num(p["entry"]),
                    M.money(q * p["entry"]), M.money(risk)))
            else:
                print("  %s: no order" % name)
            for n in notes:
                print("      - " + n)
    if a.write:
        M.save_json(M.path("orders.json"), out)
        if not a.json:
            print("Wrote %d order(s) to %s. Next: the VaR check, then the risk gate." % (len(orders), M.path("orders.json")))
    return 0


def size_pair(p, cfg, equity, cash, method):
    """Units of the pair = dollars of the first leg. Risk is the spread's move to its stop."""
    loss_per_dollar = p["max_loss_per_unit"]
    mc = p.get("montecarlo") or {}
    notes = []
    if method == "kelly":
        k = mc.get("kelly_continuous")
        if k is None:
            return None, ["no Monte Carlo odds: run the Monte Carlo first"]
        budget = max(k, 0) * float(cfg["kelly_fraction"]) * equity
        notes.append("Kelly risk budget %s" % M.money(budget))
        if budget <= 0:
            return None, notes + ["Kelly says do not bet"]
    else:
        budget = float(cfg["max_loss_per_trade_usd"])
    budget = min(budget, float(cfg["max_loss_per_trade_usd"]))
    dollars = budget / loss_per_dollar if loss_per_dollar > 0 else 0
    dollars = min(dollars, float(cfg["max_order_usd"]), float(cfg["max_position_pct"]) / 100 * equity)
    if not cfg.get("allow_short"):
        notes.append("a pair needs a short sale; the risk gate will block it unless allow_short is true")
    return (dollars if dollars >= 1 else None), notes


def pair_orders(p, dollars, idx):
    a_qty = math.floor(dollars / p["price_a"])
    b_qty = math.floor(dollars * abs(p["hedge_ratio"]) / p["price_b"])
    side_a = "buy" if p["side"] == "buy" else "sell"
    side_b = "sell" if side_a == "buy" else "buy"
    pid = "%s/%s" % (p["symbol"], p["pair_with"])
    common = {"type": "market", "time_in_force": "day", "asset_class": "us_equity"}
    return [
        dict(common, id="o%d" % idx, symbol=p["symbol"], side=side_a, qty=str(a_qty), pair_id=pid,
             plan={"setup": "pair", "pair_max_loss": round(a_qty * p["price_a"] * p["max_loss_per_unit"], 2),
                   "entry": p["price_a"], "entry_z": p["entry_z"], "spread_stop_z": p["stop_z"], "spread_target_z": p["target_z"],
                   "horizon_days": p["horizon_days"], "asof": p["asof"]}),
        dict(common, id="o%d" % (idx + 1), symbol=p["pair_with"], side=side_b, qty=str(b_qty), pair_id=pid,
             plan={"setup": "pair", "pair_max_loss": 0, "entry": p["price_b"], "entry_z": p["entry_z"],
                   "spread_stop_z": p["stop_z"], "spread_target_z": p["target_z"], "horizon_days": p["horizon_days"],
                   "asof": p["asof"], "note": "the pair's loss is counted on the first leg"}),
    ]


def cmd_optimize(a, cfg):
    tick = [M.norm_symbol(t) for t in a.tickers.split(",")]
    series = {}
    for t in tick:
        d, c = M.closes(M.load_bars(t, a.data), asof=a.asof, lookback=a.window + 1)
        series[t] = (d[1:], M.log_returns(c))
    dates, R = M.align(series)
    rows = [[R[t][i] for t in tick] for i in range(len(dates))]
    S, delta = M.ledoit_wolf(rows)
    S_ann = [[v * 252 for v in row] for row in S]
    mu = [M.mean(R[t]) * 252 for t in tick]
    if a.method == "riskparity":
        w = M.risk_parity(S_ann)
        cap_note = "risk parity has no cap: each asset adds the same risk"
    elif a.method == "minvar":
        w = M.min_variance(S_ann, cap=a.cap)
        cap_note = "cap %s per asset" % M.pct(a.cap, 0)
    else:
        # past means are a very noisy guess of future means: shrink them halfway to their average
        mbar = M.mean(mu)
        mu_s = [0.5 * m + 0.5 * mbar for m in mu]
        w = M.mean_variance(S_ann, mu_s, risk_aversion=a.risk_aversion, cap=a.cap)
        cap_note = "cap %s per asset; expected returns shrunk 50%% to their average" % M.pct(a.cap, 0)
    vol = math.sqrt(M.dot(w, M.matvec(S_ann, w)))
    rc = M.risk_contributions(S_ann, w)
    eq = [1.0 / len(tick)] * len(tick)
    out = {"asof": dates[-1], "method": a.method, "window_days": len(dates), "shrinkage": delta,
           "weights": {t: round(x, 4) for t, x in zip(tick, w)},
           "risk_contribution": {t: round(x, 4) for t, x in zip(tick, rc)},
           "vol_ann": vol, "vol_equal_weight": math.sqrt(M.dot(eq, M.matvec(S_ann, eq))),
           "past_return_ann": M.dot(w, mu), "note": cap_note}
    if a.write:
        M.save_json(M.path("targets.json"), out)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print("%s weights, %d days to %s (Ledoit-Wolf shrinkage %s toward the target)" % (
        a.method, len(dates), dates[-1], M.pct(delta, 0)))
    for t in tick:
        print("  %-8s weight %6s   share of risk %6s" % (t, M.pct(out["weights"][t]), M.pct(out["risk_contribution"][t])))
    print("  expected vol %s a year (equal weights: %s). %s." % (M.pct(vol), M.pct(out["vol_equal_weight"]), cap_note))
    print("  These are target weights for a long-term allocation, not trade signals.")
    if a.write:
        print("Wrote %s" % M.path("targets.json"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("size")
    s.add_argument("--method", choices=["kelly", "fixed"], default="kelly")
    o = sub.add_parser("optimize")
    o.add_argument("--tickers", required=True)
    o.add_argument("--method", choices=["riskparity", "minvar", "meanvar"], default="riskparity")
    o.add_argument("--cap", type=float, default=0.30)
    o.add_argument("--risk-aversion", type=float, default=4.0)
    o.add_argument("--window", type=int, default=504)
    o.add_argument("--data"); o.add_argument("--asof")
    for x in (s, o):
        x.add_argument("--config"); x.add_argument("--write", action="store_true"); x.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = M.load_config(a.config)
    return cmd_size(a, cfg) if a.cmd == "size" else cmd_optimize(a, cfg)


if __name__ == "__main__":
    sys.exit(main())
