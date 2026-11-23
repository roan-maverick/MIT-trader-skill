---
name: mit-trader
description: >-
  The MIT Trader: MIT OpenCourseWare's entire quant finance course (18.S096,
  26 lectures) as one skill. Researches the market overnight, hunting for
  strategies that really paid with the course's statistics (walk-forward
  tests, clustered t-stats, false discovery control, trading costs), and
  turns the survivors into a trading bot that looks for them every day.
  Also scans stocks, ETFs and crypto; tests any setup's edge (regression);
  forecasts volatility (GARCH); simulates 10,000 futures (Monte Carlo, Ito);
  finds beta and alpha (factor models, PCA, Kalman); sizes with Kelly;
  builds risk-parity portfolios; measures Value at Risk; checks orders
  against your limits; trades pairs (cointegration); prices options
  (Black-Scholes); plans execution; and teaches every lecture. Orders go to
  your broker on paper by default, never without your yes. Use for any
  question about trading, markets, a stock or coin, strategies, backtests,
  risk, position size, options, quant math, or this MIT course.
argument-hint: "[what you want: research, run, scan, a ticker, a question]"
---

# The MIT Trader

One skill, the whole course. MIT 18.S096 *Topics in Mathematics with
Applications in Finance* (Fall 2013): MIT mathematicians taught the math and
Morgan Stanley practitioners showed how a trading floor uses it. Every tool
here is a lecture put to work.

`${CLAUDE_SKILL_DIR}` is this skill's folder. Every tool runs as
`python3 "${CLAUDE_SKILL_DIR}/scripts/<tool>.py" ...` from the user's project
folder; results go to `./mit/`. Plain Python 3.8+, nothing to install, free
Yahoo Finance data (stocks, ETFs and crypto: BTC, ETH...).

## First time

1. If `mit/config.json` is missing, copy `${CLAUDE_SKILL_DIR}/config.example.json`
   there and ask the user for two numbers: their practice budget and their max
   loss per trade. Keep `"paper": true`.
2. Then do what they asked. If they asked for "everything" or "the bot", start
   with the overnight research below.

## The core: overnight research, then the trading bot

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" research     # overnight: hunt strategies -> mit/strategies.json, mit/research.md
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" run          # the bot: today's signals from approved rules -> tickets
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" watch        # open positions vs stops, targets, time limits
```

1. **Research (overnight).** `hunt.py` tests 51 rule variants from the course
   (dips and rips, L3 and L8; trend regressions, L6; breakouts; calm-volatility
   uptrends, L9) on the whole universe, over up to 10 years. A rule is
   **approved** only if, after trading costs, it beats ordinary days in-sample
   with false discovery controlled (Benjamini-Hochberg, 10%), with errors
   clustered by week, AND keeps paying on the last 30% of history that it never
   saw. Read `references/hunt.md`.
2. **The bot (every morning).** `autopilot.py run` looks only for the approved
   rules firing today. For each it sets a GARCH stop and target, simulates
   10,000 futures with the rule's out-of-sample edge as drift, sizes with half
   Kelly under the user's limits, checks the account's VaR and the risk gate,
   and leaves tickets for the user's yes. Read `references/autopilot.md`.
3. **If nothing is approved, the bot stands down.** Say so plainly: that is the
   math protecting the user, not a failure. On real US stocks, simple rules
   usually fail out of sample. `autopilot.py run --scan` still shows today's
   setups and tests each one.
4. **Scheduling.** Offer to create two scheduled tasks: research nightly (for
   example 2:00 AM New York) and run on weekdays at 9:50 AM; for crypto, watch
   every 2 hours. A scheduled run can only prepare tickets; the user approves.

## Everything else: pick the tool, read its guide

| the user wants | tool | read |
| --- | --- | --- |
| strategies that really paid; "research overnight"; "build me a bot" | `hunt.py`, `autopilot.py research` | `references/hunt.md` |
| the daily routine; "run it"; check positions | `autopilot.py run` / `watch` | `references/autopilot.md` |
| what is unusual in the market today | `scan.py` | `references/scanner.md` |
| "is this edge real?", "does buying the dip work?" | `signal.py` | `references/signal-lab.md` |
| volatility, where to put a stop and target | `vol.py` | `references/volatility.md` |
| the odds of a trade; "simulate it" | `montecarlo.py` | `references/montecarlo.md` |
| beta, alpha, "is it just the market?", PCA | `factors.py` | `references/factors.md` |
| how much to buy (Kelly); portfolio weights (risk parity, Markowitz) | `portfolio.py` | `references/portfolio.md` |
| "how much could I lose?" (VaR, expected shortfall) | `var.py` | `references/var.md` |
| check an order against the limits | `check.py` | `references/risk.md` |
| place, approve, record or close an order; connect Alpaca | `ticket.py` | `references/broker.md` |
| pairs trading, cointegration, market neutral | `pairs.py` | `references/pairs.md` |
| option prices, Greeks, implied vol, market-implied odds | `options.py` | `references/options.md` |
| splitting a big order | `execution.py` | `references/execution.md` |
| "explain", "teach me", "which lecture", "quiz me" | the notes | `references/professor.md`, `references/lectures/L01.md`..`L26.md` |

Read only the guides the request needs. For one stock ("should I buy NVDA?"),
the usual chain is: signal (has this setup ever paid?) -> vol plan -> montecarlo
-> factors -> portfolio size -> var -> risk, explaining each number in plain words.

## How to talk about results

- Lead with the verdict in one sentence, then the numbers that justify it.
- Translate every statistic: "t = 0.79 against a bar of 3.62: 26 past dips are
  far too few to tell a real edge from a lucky streak."
- Never call a setup a buy signal, a backtest a promise, or a risk-neutral
  probability a forecast. Never round WEAK up to EDGE.
- When the answer is "no edge", say it clearly. Most of the value of this
  course is in the trades it talks you out of.

## Files in `mit/`

| file | written by |
| --- | --- |
| `config.json` | the user (from `config.example.json`): budget and every limit |
| `strategies.json`, `research.md` | hunt: the bot's playbook |
| `candidates.json` | scan, or hunt today |
| `signals.json` | signal |
| `plan.json` | vol, pairs; montecarlo adds the odds |
| `orders.json` | portfolio; ticket close; autopilot watch |
| `var.json`, `factors.json`, `targets.json`, `pairs.json` | var, factors, portfolio optimize, pairs |
| `state/risk.json`, `state/broker.json` | the risk gate's verdicts; every yes, order and fill |
| `portfolio.json`, `prices.json` | cash and positions; latest prices |
| `report.md`, `reports/` | autopilot |

## Safety

- Education and tooling, not financial advice. Most people who trade actively lose money.
- Nothing in this skill places an order except through the broker step, and only when all three hold:
  the risk gate passed that exact order today, the user typed an explicit yes for that one order in
  the chat, and the user clicked Allow once on Claude's own card (the order tool set to "Needs approval").
  Never batch yeses. Never turn "sure" or "ok" into a yes.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config,
  with their own keys. Never ask for, read or repeat API keys in the chat.
- No options trading, margin or short selling unless the config allows it and the user confirms.
- Not affiliated with or endorsed by MIT. The lecture notes are an independent study guide (CC BY-NC-SA 4.0).
