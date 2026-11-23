#!/usr/bin/env python3
"""mit-autopilot: the whole MIT pipeline in one command, for a schedule. It never places an order.

  run    scanner -> regression -> volatility plan -> Monte Carlo -> Kelly sizing -> VaR -> risk,
         then writes mit/report.md: what it found, the odds, and any tickets ready for your yes.
  watch  checks open positions against their plans (stop, target, time limit) with the latest
         price, writes mit/prices.json, and, for crypto (which has no broker-side bracket),
         writes the closing order to mit/orders.json when a stop or target is hit.

Usage:
  autopilot.py run [--top 3] [--only-edge] [--method kelly|fixed] [--tickers A,B] [--data DIR] [--asof DATE] [--now "..."]
  autopilot.py watch [--data DIR] [--asof DATE] [--now "..."]
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mitlib as M  # noqa: E402


def tool(skill, script):
    """Sibling skills sit next to this folder (plugin, ~/.claude/skills, or this repo)."""
    base = os.path.dirname(HERE)
    for name in (skill, "mit-trader-skill:" + skill):
        p = os.path.join(base, name, script)
        if os.path.exists(p):
            return p
    raise SystemExit("cannot find %s/%s next to mit-autopilot; install the whole pack" % (skill, script))


def step(title, skill, script, args, log):
    cmd = [sys.executable, tool(skill, script)] + args
    r = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
    out = (r.stdout or "") + (("\n" + r.stderr) if r.returncode not in (0, 1) and r.stderr else "")
    log.append((title, out.strip(), r.returncode))
    return r.returncode, out


def cmd_run(a):
    cfg = M.load_config()
    data = ["--data", a.data] if a.data else []
    asof = ["--asof", a.asof] if a.asof else []
    now = ["--now", a.now] if a.now else []
    log = []
    scan_args = ["run", "--write"] + (["--tickers", a.tickers] if a.tickers else []) + data + asof
    step("1. Scanner (/mit-scanner)", "mit-scanner", "scan.py", scan_args, log)
    step("2. Signal Lab (/mit-regression)", "mit-regression", "signal.py", ["candidates", "--write"] + data + asof, log)
    vol_args = ["plan", "--from-candidates", "--top", str(a.top), "--write", "--replace"] + data + asof
    if a.only_edge or cfg.get("require_edge"):
        vol_args.append("--only-edge")
    step("3. Stops and targets (/mit-volatility)", "mit-volatility", "vol.py", vol_args, log)
    plans = (M.load_json(M.path("plan.json")) or {}).get("plans", [])
    if plans:
        step("4. Odds (/mit-montecarlo)", "mit-montecarlo", "montecarlo.py", ["run", "--write"] + data + asof, log)
        step("5. Sizing (/mit-portfolio)", "mit-portfolio", "portfolio.py", ["size", "--method", a.method, "--write"], log)
    else:
        M.save_json(M.path("orders.json"), {"orders": []})
    orders = (M.load_json(M.path("orders.json")) or {}).get("orders", [])
    if orders:
        step("6. Value at Risk (/mit-var)", "mit-var", "var.py", ["run", "--include-orders", "--write"] + data + asof, log)
        step("7. Risk check (/mit-risk)", "mit-risk", "check.py", now, log)
    risk = (M.load_json(M.path("state", "risk.json")) or {}).get("verdicts", []) if orders else []
    passed = [v for v in risk if v["verdict"] == "PASS"]
    cands = (M.load_json(M.path("candidates.json")) or {}).get("candidates", [])
    sigs = (M.load_json(M.path("signals.json")) or {}).get("results", {})
    edge = [k for k, v in sigs.items() if v.get("verdict") == "EDGE"]
    stamp = M.ny_now(a.now).strftime("%Y-%m-%d %H:%M")
    summary = [
        "# MIT Trader report, %s New York" % stamp,
        "",
        "- Setups found: %d. Proven edge (/mit-regression EDGE): %d%s." % (len(cands), len(edge), (" (" + ", ".join(edge) + ")") if edge else ""),
        "- Plans simulated: %d. Orders sized: %d. Passed /mit-risk: %d." % (len(plans), len(orders), len(passed)),
        "- %s" % ("Tickets ready for your yes: run /mit-broker show." if passed else "Nothing to approve. No trade is a fine outcome."),
        "- Account: %s. Nothing was ordered: only /mit-broker can lead to an order, after your yes." % ("PAPER" if cfg.get("paper", True) else "LIVE"),
        "",
    ]
    body = []
    for title, out, code in log:
        body += ["## " + title, "", "```", out or "(no output)", "```", ""]
    text = "\n".join(summary + body)
    with open(M.path("report.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    hist = M.path("reports")
    os.makedirs(hist, exist_ok=True)
    with open(os.path.join(hist, stamp.replace(":", "").replace(" ", "_") + ".md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    print("\n".join(summary))
    print("Full report: %s" % M.path("report.md"))
    return 0


def cmd_watch(a):
    pf = M.load_json(M.path("portfolio.json"))
    if not pf or not pf.get("positions"):
        print("No open positions in mit/portfolio.json.")
        return 0
    now = M.ny_now(a.now)
    prices, exits, lines = {}, [], []
    for p in pf["positions"]:
        sym = M.norm_symbol(p["symbol"])
        bars = M.load_bars(sym, a.data, refresh=not a.data, max_age_hours=0.05)
        if a.data or not bars.get("last"):
            d, c = M.closes(bars, asof=a.asof)
            px, when = c[-1], d[-1]
        else:
            px, when = bars["last"]["price"], bars["last"]["time"]
        prices[sym] = {"price": px, "source": when, "ny_time": now.strftime("%Y-%m-%d %H:%M")}
        plan = p.get("plan") or {}
        qty = float(p["qty"])
        long = qty > 0
        stop, tgt = plan.get("stop"), plan.get("target")
        hit = None
        if stop is not None and ((long and px <= stop) or (not long and px >= stop)):
            hit = "stop"
        elif tgt is not None and ((long and px >= tgt) or (not long and px <= tgt)):
            hit = "target"
        elif plan.get("asof") and plan.get("horizon_days"):
            start = dt.datetime.strptime(plan["asof"], "%Y-%m-%d")
            if (now - start).days > int(plan["horizon_days"]) * 7 / 5 + 1:
                hit = "time"
        msg = "%-8s %s units at %s: stop %s, target %s" % (sym, M.num(qty, 6).rstrip("0").rstrip("."), M.num(px), M.num(stop), M.num(tgt))
        if hit:
            msg += "  -> %s %s" % (hit.upper(), "reached" if hit != "time" else "limit passed (the plan's horizon is over)")
            if M.is_crypto(sym) or hit == "time":
                exits.append({"id": "x%d" % (len(exits) + 1), "symbol": M.broker_symbol(sym), "asset_class": M.asset_class(sym),
                              "side": "sell" if long else "buy",
                              "qty": ("%.8f" % abs(qty)).rstrip("0").rstrip(".") if M.is_crypto(sym) else str(int(abs(qty))),
                              "type": "market", "time_in_force": "gtc" if M.is_crypto(sym) else "day",
                              "plan": {"setup": "exit", "reason": hit}})
            else:
                msg += " (the broker's bracket handles it; record the fill with /mit-broker fill)"
        lines.append(msg)
    M.save_json(M.path("prices.json"), prices)
    print("Positions at %s New York:" % now.strftime("%Y-%m-%d %H:%M"))
    for l in lines:
        print("  " + l)
    if exits:
        M.save_json(M.path("orders.json"), {"asof": now.strftime("%Y-%m-%d"), "orders": exits})
        print("Wrote %d closing order(s) to mit/orders.json. Next: /mit-risk, then /mit-broker show and your yes." % len(exits))
    else:
        print("Nothing to do.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--top", type=int, default=3)
    r.add_argument("--only-edge", action="store_true")
    r.add_argument("--method", choices=["kelly", "fixed"], default="kelly")
    r.add_argument("--tickers")
    w = sub.add_parser("watch")
    for s in (r, w):
        s.add_argument("--data"); s.add_argument("--asof"); s.add_argument("--now")
    a = ap.parse_args(argv)
    os.makedirs(M.mit_dir(), exist_ok=True)
    return cmd_run(a) if a.cmd == "run" else cmd_watch(a)


if __name__ == "__main__":
    sys.exit(main())
