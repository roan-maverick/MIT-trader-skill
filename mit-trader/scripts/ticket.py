#!/usr/bin/env python3
"""mit-trader / broker: turn risk-passed orders into plain tickets, record your yes, log what happened.

ticket.py never talks to a broker. Claude does, through your brokerage
connector (Alpaca's MCP server, paper account by default), and only after:
  1. the risk gate passed this exact order today (matched by fingerprint),
  2. you typed an explicit yes for this one order in the chat (recorded here),
  3. you clicked Allow once on Claude's own permission card.

Usage:
  ticket.py show                                   # every ticket: READY, NOT READY or BLOCKED
  ticket.py approve --index 1 --reply "yes"        # records your reply, word for word
  ticket.py result --index 1 --status placed --broker-id ID [--filled-qty 6 --filled-price 125.60]
  ticket.py fill --symbol NVDA --side sell --qty 6 --price 109.43     # a stop or target filled
  ticket.py close --symbol NVDA --qty 6            # writes a sell that closes a position
  ticket.py log
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mitlib as M  # noqa: E402

YES = ("yes", "y")
REFUSE = ("all", "every", "everything", "both")
STOCK_FIELDS = ("symbol", "side", "qty", "type", "time_in_force", "limit_price", "order_class",
                "take_profit_limit_price", "stop_loss_stop_price")
CRYPTO_FIELDS = ("symbol", "side", "qty", "type", "time_in_force", "limit_price")


def broker_log():
    return M.load_json(M.path("state", "broker.json")) or {"entries": []}


def save_log(doc):
    M.save_json(M.path("state", "broker.json"), doc)


def tool_call(o):
    """The exact tool and arguments Claude sends to Alpaca's MCP server."""
    crypto = o.get("asset_class") == "crypto" or M.is_crypto(o["symbol"])
    fields = CRYPTO_FIELDS if crypto else STOCK_FIELDS
    args = {k: o[k] for k in fields if o.get(k) is not None}
    args["symbol"] = M.broker_symbol(o["symbol"])
    return ("place_crypto_order" if crypto else "place_stock_order"), args


def status(o, risk, now):
    v = {x["id"]: x for x in (risk or {}).get("verdicts", [])}.get(o.get("id"))
    if not v:
        return "NOT READY", "no risk-gate verdict for this order: run check.py", None
    if risk.get("date") != now.strftime("%Y-%m-%d"):
        return "NOT READY", "the risk check is from %s, not today: run check.py again" % risk.get("date"), v
    if v["fingerprint"] != M.fingerprint(o):
        return "NOT READY", "the order changed after the risk gate checked it: run check.py again", v
    if v["verdict"] != "PASS":
        return "BLOCKED", "; ".join(v["reasons"]), v
    log = broker_log()
    for e in reversed(log["entries"]):
        if e.get("fingerprint") == v["fingerprint"] and e.get("date") == now.strftime("%Y-%m-%d"):
            if e["status"] == "approved":
                return "APPROVED", "your yes is recorded (%s); waiting for the order call" % e.get("at"), v
            if e["status"] in ("placed", "filled"):
                return "DONE", "already placed today (%s)" % e.get("broker_id", ""), v
            if e["status"] in ("denied", "failed"):
                return "NOT READY", "last attempt %s; needs a new the risk gate check and a new yes" % e["status"], v
    return "READY", "passed the risk gate at %s" % risk.get("checked_at"), v


def describe(o, v):
    crypto = o.get("asset_class") == "crypto" or M.is_crypto(o["symbol"])
    side = "Buy" if o["side"] == "buy" else "Sell"
    how = "at market" if o.get("type", "market") == "market" else "limit %s" % o.get("limit_price")
    lines = ["%s %s %s %s, %s" % (side, o["qty"], M.broker_symbol(o["symbol"]), how,
                                  "good till canceled" if o.get("time_in_force") == "gtc" else "today only")]
    if o.get("order_class") == "bracket":
        lines.append("with a stop-loss at %s and a take-profit at %s (they cancel each other)" % (
            o["stop_loss_stop_price"], o["take_profit_limit_price"]))
    elif crypto and (o.get("plan") or {}).get("stop"):
        lines.append("stop %s and target %s are watched by the autopilot watch (Alpaca has no crypto brackets)" % (
            M.num(o["plan"]["stop"]), M.num(o["plan"]["target"])))
    if o.get("pair_id"):
        lines.append("one leg of the pair %s" % o["pair_id"])
    if v and v.get("max_loss") is not None:
        lines.append("max loss at the stop: %s" % M.money(v["max_loss"]))
    return lines


def is_yes(reply, o):
    words = [w.strip(".,!?\"'").lower() for w in reply.split()]
    if not words or words[0] not in YES:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    if any(w in REFUSE for w in words):
        return False, "one order per yes: \"yes to all\" is not accepted"
    sym = M.broker_symbol(o["symbol"]).upper()
    ok_names = {sym, sym.split("/")[0], sym.replace("/", ""), "YES", "Y", "I", "OK", "USD"}
    raw = [w.strip(".,!?\"'") for w in reply.split()]
    other = [w for w in raw[1:] if w.isalpha() and w.isupper() and len(w) <= 5 and w not in ok_names]
    if other:
        return False, "the reply names %s, not %s" % (", ".join(other), sym)
    nums = [w for w in words if w.replace(".", "", 1).isdigit()]
    if nums and str(o["qty"]) not in nums:
        return False, "the reply names a different amount (%s) than the order (%s)" % (", ".join(nums), o["qty"])
    return True, ""


def orders_and_risk():
    return (M.load_json(M.path("orders.json")) or {}).get("orders", []), M.load_json(M.path("state", "risk.json"))


def cmd_show(a, cfg, now):
    orders, risk = orders_and_risk()
    if not orders:
        print("No orders. Nothing to send.")
        return 0
    acct = "PAPER" if cfg.get("paper", True) else "LIVE"
    for i, o in enumerate(orders, 1):
        st, why, v = status(o, risk, now)
        print("#%d %s  (%s account)" % (i, st, acct))
        for line in describe(o, v):
            print("   " + line)
        print("   " + why)
        if st == "READY":
            tool, args = tool_call(o)
            print("   Claude will call %s with exactly:" % tool)
            print("   " + json.dumps(args))
    return 0


def find(index):
    orders, risk = orders_and_risk()
    if index < 1 or index > len(orders):
        raise SystemExit("No ticket #%d" % index)
    return orders[index - 1], risk


def cmd_approve(a, cfg, now):
    o, risk = find(a.index)
    st, why, v = status(o, risk, now)
    if st != "READY":
        print("Not recorded: ticket #%d is %s (%s)." % (a.index, st, why))
        return 1
    ok, msg = is_yes(a.reply, o)
    log = broker_log()
    entry = {"date": now.strftime("%Y-%m-%d"), "at": now.strftime("%H:%M"), "symbol": o["symbol"], "side": o["side"],
             "qty": o["qty"], "reply": a.reply, "fingerprint": v["fingerprint"], "kind": v["kind"],
             "max_loss": v.get("max_loss"), "paper": bool(cfg.get("paper", True))}
    if not ok:
        entry["status"] = "no"
        log["entries"].append(entry)
        save_log(log)
        print("Not recorded as a yes: %s. Ask again; never turn a reply into a yes." % msg)
        return 1
    entry["status"] = "approved"
    log["entries"].append(entry)
    save_log(log)
    tool, args = tool_call(o)
    print("Recorded your yes for ticket #%d at %s." % (a.index, entry["at"]))
    print("Now call %s with exactly:" % tool)
    print(json.dumps(args))
    return 0


def cmd_result(a, cfg, now):
    o, risk = find(a.index)
    st, why, v = status(o, risk, now)
    if st != "APPROVED":
        print("Not recorded: ticket #%d is %s; a result is recorded only after an approved yes." % (a.index, st))
        return 1
    log = broker_log()
    e = {"date": now.strftime("%Y-%m-%d"), "at": now.strftime("%H:%M"), "symbol": o["symbol"], "side": o["side"],
         "qty": o["qty"], "status": a.status, "broker_id": a.broker_id, "note": a.note, "fingerprint": v["fingerprint"],
         "kind": v["kind"], "max_loss": v.get("max_loss"), "paper": bool(cfg.get("paper", True))}
    log["entries"].append(e)
    save_log(log)
    if a.status == "placed" and a.filled_qty:
        update_portfolio(o["symbol"], o["side"], a.filled_qty, a.filled_price or (o.get("plan") or {}).get("entry"), o.get("plan"))
    print("Recorded: ticket #%d %s%s." % (a.index, a.status, (" (" + a.broker_id + ")") if a.broker_id else ""))
    return 0


def update_portfolio(sym, side, qty, price, plan=None):
    cfg = M.load_config()
    pth = M.path("portfolio.json")
    pf = M.load_json(pth) or {"cash": float(cfg["budget"]), "positions": []}
    sym = M.norm_symbol(sym)
    q = float(qty) * (1 if side == "buy" else -1)
    pf["cash"] = round(float(pf["cash"]) - q * float(price), 2)
    for p in pf["positions"]:
        if M.norm_symbol(p["symbol"]) == sym:
            p["qty"] = round(float(p["qty"]) + q, 8)
            p["price"] = float(price)
            break
    else:
        pf["positions"].append({"symbol": sym, "qty": q, "price": float(price), "avg_price": float(price)})
    if plan:
        for p in pf["positions"]:
            if M.norm_symbol(p["symbol"]) == sym:
                p["plan"] = {k: plan.get(k) for k in ("stop", "target", "setup", "horizon_days", "asof")}
    pf["positions"] = [p for p in pf["positions"] if abs(float(p["qty"])) > 1e-12]
    M.save_json(pth, pf)


def cmd_fill(a, cfg, now):
    update_portfolio(a.symbol, a.side, a.qty, a.price)
    log = broker_log()
    log["entries"].append({"date": now.strftime("%Y-%m-%d"), "at": now.strftime("%H:%M"), "symbol": M.norm_symbol(a.symbol),
                           "side": a.side, "qty": str(a.qty), "status": "filled", "price": a.price, "kind": "exit"})
    save_log(log)
    print("Recorded the fill: %s %s %s at %s. mit/portfolio.json updated." % (a.side, a.qty, M.norm_symbol(a.symbol), a.price))
    return 0


def cmd_close(a, cfg, now):
    sym = M.norm_symbol(a.symbol)
    crypto = M.is_crypto(sym)
    o = {"id": "x1", "symbol": M.broker_symbol(sym), "asset_class": M.asset_class(sym), "side": "sell" if a.qty > 0 else "buy",
         "qty": ("%.8f" % abs(a.qty)).rstrip("0").rstrip(".") if crypto else str(int(abs(a.qty))),
         "type": "market", "time_in_force": "gtc" if crypto else "day", "plan": {"setup": "exit"}}
    M.save_json(M.path("orders.json"), {"asof": now.strftime("%Y-%m-%d"), "orders": [o]})
    print("Wrote a closing order to mit/orders.json: %s %s %s at market." % (o["side"], o["qty"], o["symbol"]))
    print("Next: check.py (an exit is never blocked by day limits), then ticket.py show and your yes.")
    if not crypto:
        print("If a bracket still holds these shares, cancel its legs first (get_orders, then cancel_order_by_id).")
    return 0


def cmd_log(a, cfg, now):
    for e in broker_log()["entries"][-30:]:
        print("%s %s %-8s %-4s %-8s %s %s" % (e.get("date"), e.get("at", ""), e.get("status"), e.get("side"), e.get("symbol"),
                                            e.get("qty"), ("max loss " + M.money(e["max_loss"])) if e.get("max_loss") else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("approve"); p.add_argument("--index", type=int, required=True); p.add_argument("--reply", required=True)
    r = sub.add_parser("result"); r.add_argument("--index", type=int, required=True)
    r.add_argument("--status", choices=["placed", "denied", "failed"], required=True)
    r.add_argument("--broker-id", default=""); r.add_argument("--note", default="")
    r.add_argument("--filled-qty", type=float); r.add_argument("--filled-price", type=float)
    f = sub.add_parser("fill"); f.add_argument("--symbol", required=True); f.add_argument("--side", choices=["buy", "sell"], required=True)
    f.add_argument("--qty", type=float, required=True); f.add_argument("--price", type=float, required=True)
    c = sub.add_parser("close"); c.add_argument("--symbol", required=True); c.add_argument("--qty", type=float, required=True)
    sub.add_parser("log")
    a = ap.parse_args(argv)
    cfg = M.load_config()
    now = M.ny_now(a.now)
    return {"show": cmd_show, "approve": cmd_approve, "result": cmd_result, "fill": cmd_fill,
            "close": cmd_close, "log": cmd_log}[a.cmd](a, cfg, now)


if __name__ == "__main__":
    sys.exit(main())
