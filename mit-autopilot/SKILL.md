---
name: mit-autopilot
description: >-
  Autopilot. Runs the whole MIT pipeline in one command for a schedule:
  /mit-scanner, /mit-regression, /mit-volatility plans, /mit-montecarlo odds,
  /mit-portfolio Kelly sizing, /mit-var and /mit-risk, then writes
  mit/report.md (and a dated copy in mit/reports/) with what it found, the
  odds, and any tickets ready for the user's yes. Its watch mode checks open
  positions against their stops, targets and time limits with the latest
  price, and writes the closing order for crypto, which has no broker-side
  stop. It never places an order. Use when the user says "run everything",
  "daily routine", "run the pipeline", "set up my trading bot", "run this
  every day", "check my positions", "24/7", or when a scheduled task fires.
argument-hint: "[run | watch]"
---

# mit-autopilot

The "trading bot" part of the pack: research on a schedule, honest report,
your yes for every order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder. It calls the other skills'
tools from their folders next to this one, so the whole pack must be installed.

```bash
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" run                  # top 3 plans, Kelly sizing
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" run --only-edge      # plan only setups rated EDGE
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" run --tickers BTC,ETH,SPY,QQQ,NVDA
python3 "${CLAUDE_SKILL_DIR}/autopilot.py" watch                # positions vs stops and targets
```

## What it does, in order

1. `/mit-scanner run --write`: setups across the universe.
2. `/mit-regression candidates --write`: EDGE, WEAK or NONE for each.
3. `/mit-volatility plan --from-candidates --top 3 --write --replace`: EDGE first.
4. `/mit-montecarlo run --write`: odds, with drift only from measured edge.
5. `/mit-portfolio size --write`: Kelly; zero means no order.
6. `/mit-var run --include-orders --write` and `/mit-risk`.
7. Writes `mit/report.md`. Tickets that passed wait for the user in /mit-broker.

`watch` reads `mit/portfolio.json`, gets the latest price for each position,
writes `mit/prices.json` (which /mit-risk uses as a fresh price), and flags any
position past its stop, target or time limit. For crypto, or a time limit, it
writes the closing order to `mit/orders.json` for /mit-risk and the user's yes.
Stock stops and targets are handled at the broker by the bracket.

## Running it on a schedule

- **Claude (desktop or web):** ask "every weekday at 9:50 AM New York, run
  /mit-autopilot run and send me the report". Claude creates a scheduled task.
  For crypto, "every 2 hours, run /mit-autopilot watch".
- **Claude Code:** a scheduled task, or cron on your own machine:
  `50 9 * * 1-5 cd ~/trading && claude -p "/mit-autopilot run, then summarize mit/report.md"`
- A scheduled run has nobody to say yes, so it can only prepare tickets. That
  is by design. You approve each order when you read the report.

## Steps

1. Run it. Read `mit/report.md`.
2. Tell the user in a few lines: setups found, how many have a proven edge,
   the odds of what was planned, what was sized, what passed /mit-risk.
3. If tickets are READY, show them one at a time with /mit-broker. If not, say
   that no trade is a fine outcome.

## Example: Monday November 23, 2026, 10:00 New York (real data to Nov 20)

```
- Setups found: 32. Proven edge (/mit-regression EDGE): 0.
- Plans simulated: 3. Orders sized: 2. Passed /mit-risk: 2.
```

The three plans were the WEAK dips (GDX, MSFT, KLAC). Kelly sized MSFT and
KLAC, whose small measured edge survived the credibility shrink, and gave GDX
nothing. Both still carry the warning "no proven edge".

## Safety

- Education and tooling, not financial advice. Most traders lose money; a bot does not change that.
- It never places an order. Only /mit-broker can lead to one, after /mit-risk passes that exact
  order and the user types yes for it and clicks Allow once.
- Paper trading by default. Run it on paper for weeks before considering anything else.
