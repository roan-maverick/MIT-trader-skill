#!/usr/bin/env python3
"""mit-risk: the gate between a proposed order and your broker. PASS or BLOCK, with the reason.

Reads mit/orders.json and checks each order against your limits in
mit/config.json, in file order, as if each passed order had filled. A BLOCK
is final for that order. A PASS only means the order may be shown to you; it
is not a yes.

Usage:
  check.py [--orders mit/orders.json] [--now "2026-11-23 10:00"] [--no-write] [--json]
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

STOCK_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
OPTION_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_state(cfg, now):
    pf = M.load_json(M.path("portfolio.json"))
    if pf:
        cash = float(pf.get("cash", 0))
        held = {}
        for p in pf.get("positions", []):
            s = M.norm_symbol(p["symbol"])
            held[s] = held.get(s, 0.0) + float(p.get("qty", 0))
        prices = {M.norm_symbol(p["symbol"]): float(p.get("price", p.get("avg_price", 0))) for p in pf.get("positions", [])}
        equity = cash + sum(held[s] * prices.get(s, 0) for s in held)
        src = "mit/portfolio.json"
    else:
        cash = equity = float(cfg["budget"])
        held, src = {}, "a fresh account funded with your budget"
    log = (M.load_json(M.path("state", "broker.json")) or {}).get("entries", [])
    today = now.strftime("%Y-%m-%d")
    placed_today = [e for e in log if e.get("date") == today and e.get("status") in ("placed", "filled")]
    return {"cash": cash, "equity": equity, "held": held, "account": src, "placed_today": placed_today}


def fresh_price(sym, now):
    doc = M.load_json(M.path("prices.json")) or {}
    p = doc.get(M.norm_symbol(sym))
    if not p:
        return None, None
    try:
        t = M._dt.datetime.strptime(p["ny_time"], "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return None, None
    age = (now - t).total_seconds() / 60
    return (float(p["price"]), age) if 0 <= age <= 15 else (None, age)


def check(orders, cfg, now, state):
    out = []
    cash = state["cash"]
    equity = state["equity"]
    held = dict(state["held"])
    entries_today = [e for e in state["placed_today"] if e.get("kind") == "entry"]
    day_loss = sum(float(e.get("max_loss") or 0) for e in entries_today)
    trades = len(entries_today)
    n_orders = len(state["placed_today"])
    seen = set((M.norm_symbol(e["symbol"]), e["side"]) for e in entries_today)
    var_doc = M.load_json(M.path("var.json")) or {}
    sig_doc = (M.load_json(M.path("signals.json")) or {}).get("results", {})
    is_open, _, _, sess_note = M.market_session(now)
    hhmm = now.strftime("%H:%M")
    for o in orders:
        why, warn = [], []
        sym = M.norm_symbol(o.get("symbol", ""))
        side = o.get("side")
        qty = _f(o.get("qty"))
        crypto = M.is_crypto(sym)
        plan = o.get("plan") or {}
        # ---- format
        if not sym:
            why.append("format: no symbol")
        if side not in ("buy", "sell"):
            why.append("format: side must be buy or sell")
        if qty is None or qty <= 0:
            why.append("format: qty must be a positive number")
        elif not crypto and not cfg.get("fractional") and qty != int(qty):
            why.append("format: whole shares only (fractional is off)")
        if not isinstance(o.get("qty"), str):
            warn.append("qty should be a string in broker JSON")
        if o.get("type") == "limit" and _f(o.get("limit_price")) is None:
            why.append("format: a limit order needs limit_price")
        if o.get("order_class") == "bracket":
            if crypto:
                why.append("format: Alpaca has no bracket orders for crypto")
            if o.get("time_in_force") not in ("day", "gtc"):
                why.append("format: a bracket must be day or gtc")
            if _f(o.get("stop_loss_stop_price")) is None or _f(o.get("take_profit_limit_price")) is None:
                why.append("format: a bracket needs both stop_loss_stop_price and take_profit_limit_price")
        # ---- asset
        if OPTION_RE.match(sym.replace("-", "")) and not cfg.get("allow_options"):
            why.append("asset: options are off (allow_options false)")
        elif crypto and not cfg.get("allow_crypto", True):
            why.append("asset: crypto is off (allow_crypto false)")
        elif not crypto and not STOCK_RE.match(sym):
            why.append("asset: %s is not a US stock / ETF ticker or a supported coin" % sym)
        # ---- entry or exit
        have = held.get(sym, 0.0)
        is_exit = (side == "sell" and have > 0 and qty is not None and qty <= have + 1e-9) or \
                  (side == "buy" and have < 0 and qty is not None and qty <= -have + 1e-9)
        if side == "sell" and qty is not None and qty > have + 1e-9 and not cfg.get("allow_short"):
            why.append("short: selling %s but you hold %s (allow_short is false)" % (M.num(qty, 6).rstrip("0").rstrip("."), M.num(have, 6).rstrip("0").rstrip(".")))
        entry = _f(plan.get("entry"))
        if o.get("type") == "limit":
            entry = _f(o.get("limit_price"))
        else:
            fp, age = fresh_price(sym, now)
            if fp and entry:
                entry = max(entry, fp) if side == "buy" else min(entry, fp)
            elif age is not None and age > 15:
                warn.append("the last price is %d min old; not used" % age)
        stop = _f(o.get("stop_loss_stop_price")) or _f(plan.get("stop"))
        target = _f(o.get("take_profit_limit_price")) or _f(plan.get("target"))
        loss = rr = None
        rules = []  # (name, message) that block entries but only warn for exits
        if plan.get("setup") == "pair":
            loss = _f(plan.get("pair_max_loss")) or 0.0
            if plan.get("spread_stop_z") is None:
                rules.append(("stop", "a pair needs a spread stop"))
            ez, tz, sz = _f(plan.get("entry_z")), _f(plan.get("spread_target_z")), _f(plan.get("spread_stop_z"))
            if None not in (ez, tz, sz) and abs(sz - ez) > 0:
                rr = abs(tz - ez) / abs(sz - ez)
        else:
            if stop is None:
                if cfg.get("require_stop"):
                    rules.append(("stop", "no stop (require_stop is true)"))
            elif entry:
                if (side == "buy" and stop >= entry) or (side == "sell" and stop <= entry):
                    rules.append(("stop", "the stop %s is on the wrong side of the entry %s" % (M.num(stop), M.num(entry))))
                else:
                    loss = (qty or 0) * abs(entry - stop)
                    if target:
                        rr = abs(target - entry) / abs(entry - stop)
            if crypto and stop is not None:
                warn.append("crypto: the stop lives in the plan, not at the broker; /mit-autopilot watch must be running")
        if loss is not None and loss > float(cfg["max_loss_per_trade_usd"]) + 1e-9:
            rules.append(("loss", "%s at the stop, over your %s max loss per trade" % (M.money(loss), M.money(cfg["max_loss_per_trade_usd"]))))
        if rr is not None and rr + 1e-9 < float(cfg["min_reward_risk"]):
            rules.append(("reward:risk", "%.2f, under your minimum %s" % (rr, cfg["min_reward_risk"])))
        if loss is not None and day_loss + loss > float(cfg["max_daily_loss_usd"]) + 1e-9:
            rules.append(("daily loss", "today's max losses would reach %s, over your %s daily limit" % (M.money(day_loss + loss), M.money(cfg["max_daily_loss_usd"]))))
        if trades >= int(cfg["max_trades_per_day"]):
            rules.append(("trades", "%d entries already today (max %s)" % (trades, cfg["max_trades_per_day"])))
        if n_orders >= int(cfg["max_orders_per_day"]):
            rules.append(("daily limit", "%d orders already today (max %s)" % (n_orders, cfg["max_orders_per_day"])))
        if sym in [M.norm_symbol(b) for b in cfg.get("blocked", [])]:
            rules.append(("blocked", "%s is on your blocked list" % sym))
        notional = (qty or 0) * (entry or 0)
        if notional and notional < float(cfg["min_order_usd"]):
            rules.append(("size", "%s is under your %s minimum" % (M.money(notional), M.money(cfg["min_order_usd"]))))
        if notional > float(cfg["max_order_usd"]) + 1e-9:
            rules.append(("size", "%s is over your %s maximum order" % (M.money(notional), M.money(cfg["max_order_usd"]))))
        if equity > 0 and notional + abs(have) * (entry or 0) > float(cfg["max_position_pct"]) / 100 * equity + 1e-6:
            rules.append(("position", "%s would be over %s%% of your %s account" % (sym, cfg["max_position_pct"], M.money(equity))))
        if side == "buy" and notional > cash - float(cfg["cash_buffer_pct"]) / 100 * equity + 1e-6:
            rules.append(("cash", "needs %s; cash after the %s%% buffer is %s%s" % (
                M.money(notional), cfg["cash_buffer_pct"], M.money(cash - float(cfg["cash_buffer_pct"]) / 100 * equity),
                "" if cfg.get("allow_margin") else " (no margin)")))
        if not crypto:
            if not is_open:
                rules.append(("window", "the stock market is closed (%s)" % (sess_note or "outside 9:30-16:00 New York")))
            else:
                if cfg.get("no_entries_before") and hhmm < cfg["no_entries_before"]:
                    rules.append(("window", "before %s New York (no new entries yet)" % cfg["no_entries_before"]))
                if cfg.get("no_entries_after") and hhmm > cfg["no_entries_after"]:
                    rules.append(("window", "after %s New York" % cfg["no_entries_after"]))
            if sess_note == "early close 1:00 PM":
                warn.append("early close today")
        if (sym, side) in seen:
            rules.append(("duplicate", "%s %s already placed today or earlier in this batch" % (side, sym)))
        # VaR: the account's 1-day 99% VaR with this order in it
        if var_doc and o.get("id") in var_doc.get("includes_orders", []):
            if float(var_doc.get("var_pct", 0)) > float(cfg["max_var_pct"]) + 1e-9:
                rules.append(("VaR", "1-day VaR with your orders is %s of equity, over your %s%% limit" % (
                    M.pct(var_doc["var_pct"] / 100, 2), cfg["max_var_pct"])))
        elif not is_exit:
            warn.append("no VaR for this order yet: run /mit-var run --include-orders --write")
        key = "%s:%s" % (sym, plan.get("setup"))
        v = sig_doc.get(key, {}).get("verdict")
        if v in ("NONE", "WEAK") and not is_exit:
            msg = "/mit-regression rated this setup %s" % v
            if cfg.get("require_edge"):
                rules.append(("edge", msg + " (require_edge is true)"))
            else:
                warn.append(msg + ": no proven edge")
        if not cfg.get("paper", True):
            warn.append("LIVE account (paper is false)")
        for name, msg in rules:
            if is_exit:
                warn.append("%s: %s (an exit is never blocked by this)" % (name, msg))
            else:
                why.append("%s: %s" % (name, msg))
        verdict = "BLOCK" if why else "PASS"
        if verdict == "PASS":
            if not is_exit:
                trades += 1
                day_loss += loss or 0
                seen.add((sym, side))
            n_orders += 1
            if side == "buy":
                cash -= notional
                held[sym] = have + (qty or 0)
            else:
                cash += notional
                held[sym] = have - (qty or 0)
        out.append({"id": o.get("id"), "symbol": sym, "side": side, "qty": o.get("qty"), "kind": "exit" if is_exit else "entry",
                    "verdict": verdict, "reasons": why, "warnings": warn, "entry": entry, "stop": stop,
                    "target": target, "max_loss": round(loss, 2) if loss is not None else None,
                    "reward_risk": round(rr, 2) if rr is not None else None,
                    "fingerprint": M.fingerprint(o), "day_loss_after": round(day_loss, 2), "trades_after": trades})
    return out, cash


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders")
    ap.add_argument("--now", help='pin the clock, New York time: "2026-11-23 10:00"')
    ap.add_argument("--config")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = M.load_config(a.config)
    now = M.ny_now(a.now)
    doc = M.load_json(a.orders or M.path("orders.json"))
    if not doc or not doc.get("orders"):
        print("No orders to check (mit/orders.json is empty). Nothing can be sent.")
        return 0
    state = load_state(cfg, now)
    res, cash_after = check(doc["orders"], cfg, now, state)
    stamp = now.strftime("%Y-%m-%d %H:%M")
    if not a.no_write:
        M.save_json(M.path("state", "risk.json"), {"checked_at": stamp, "date": now.strftime("%Y-%m-%d"), "verdicts": res})
    if a.json:
        print(json.dumps({"checked_at": stamp, "verdicts": res, "cash_after": cash_after}, indent=2))
    else:
        for i, r in enumerate(res, 1):
            print("%-5s #%d %s %s %s, %s" % (r["verdict"], i, r["side"], r["symbol"], r["qty"], r["kind"]))
            if r["max_loss"] is not None:
                print("          entry %s, stop %s, target %s: max loss %s (limit %s), reward:risk %s (min %s)" % (
                    M.num(r["entry"]), M.num(r["stop"]), M.num(r["target"]), M.money(r["max_loss"]),
                    M.money(cfg["max_loss_per_trade_usd"]), M.num(r["reward_risk"]), cfg["min_reward_risk"]))
            for w in r["reasons"]:
                print("        - " + w)
            for w in r["warnings"]:
                print("        ! " + w)
        npass = sum(1 for r in res if r["verdict"] == "PASS")
        print("\n%d passed, %d blocked at %s New York. Account: %s. Cash after the passed orders: %s (%s account)." % (
            npass, len(res) - npass, stamp, state["account"], M.money(cash_after), "paper" if cfg.get("paper", True) else "LIVE"))
    return 0 if all(r["verdict"] == "PASS" for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
