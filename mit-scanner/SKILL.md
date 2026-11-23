---
name: mit-scanner
description: >-
  Statistical Scanner. Scans a universe of US stocks, ETFs and crypto (40+
  names by default, any list you give it) on daily closes for four setups
  built on MIT 18.S096 math: dip (price 2+ standard deviations below its
  20-day mean), rip (2+ above), trend (63-day log-price regression t-stat of
  3 or more) and slide (-3 or less). Reports each symbol's z-score, 5- and
  21-day moves, volatility, trend t-stat and Ornstein-Uhlenbeck half-life,
  and counts how many tests it ran so /mit-regression can raise the bar for
  luck. Use when the user says "scan the market", "what's oversold", "find
  setups", "any dips", "what's trending", "scan my watchlist", "scan crypto",
  or at the start of /mit-autopilot.
argument-hint: "[tickers, comma separated]"
---

# mit-scanner

The first step of the pipeline. It looks for prices that are statistically
unusual today. Unusual is not the same as profitable: whether a setup has
ever paid is /mit-regression's job, and it is usually "no".

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" run --write                       # the universe in mit/config.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" run --tickers NVDA,TSLA,BTC --write
python3 "${CLAUDE_SKILL_DIR}/scan.py" run --top 10 --json
python3 "${CLAUDE_SKILL_DIR}/scan.py" stats NVDA
python3 "${CLAUDE_SKILL_DIR}/scan.py" run --data tests/fixtures/bars --asof 2026-11-20   # offline, repeatable
```

Data: free Yahoo Finance daily bars (adjusted closes), cached in `mit/bars/`
for 12 hours. Crypto works with any spelling: BTC, BTC/USD and BTC-USD all
mean Bitcoin.

## What it reads and writes

| file | what |
| --- | --- |
| `mit/config.json` | `universe` (the default list if missing) |
| `mit/bars/SYMBOL.json` | the price cache |
| `mit/candidates.json` | the setups found, every symbol's stats, and `n_tests` |

## The setups and the math behind them

| setup | rule | lecture |
| --- | --- | --- |
| dip | z = (log price - 20-day mean) / 20-day std <= -2 | L3 normal distribution, L8 mean reversion |
| rip | z >= +2 (a short; only traded if `allow_short`) | same |
| trend | slope t-stat of log price on time, 63 days, Newey-West errors, >= 3 | L6 regression |
| slide | the same t-stat <= -3 (a warning, never a buy) | L6 |

Also reported: the Ornstein-Uhlenbeck half-life of the log price over 120
days (L21), annualized 20-day volatility, 5- and 21-day returns.

## Steps

1. Run `scan.py run --write`.
2. Tell the user the setups in plain words, biggest first: the symbol, what is
   unusual about it and how unusual (for example "NVDA is 2.3 standard
   deviations below its 20-day average after falling 41% in a month").
3. Say how many tests were run and why that matters: with 168 tests a few
   will look special by luck alone.
4. Next: `/mit-regression candidates` to test whether any of these setups has
   ever paid.

## Example: Friday November 20, 2026 (real data)

The market had sold off for a month (NVDA -41%, SPY -10% in 21 days). Of 42
symbols, 32 showed a setup: 22 dips, 5 trends, 4 slides. NVDA:

```
NVDA     dip    close 125.53  5d -22.9%  21d -40.8%  vol 69%  2.29 std below its 20-day mean (179.43)
```

168 tests in all (42 symbols x 4 rules).

## Rules

- A setup is a question, not an answer. Never call a setup a buy signal.
- Every number comes from the data. If a symbol is missing, say it was skipped.

## Safety

- Education and tooling, not financial advice. Most traders lose money.
- Nothing here places an order. Only /mit-broker can lead to one, after /mit-risk passes it and the
  user types an explicit yes for that one order and clicks Allow once on Claude's own card.
- Paper trading by default (`"paper": true`).
