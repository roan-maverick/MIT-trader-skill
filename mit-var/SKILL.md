---
name: mit-var
description: >-
  Value at Risk. Estimates how much the whole account could lose in one day
  at 99% confidence, with proposed orders counted as filled, three ways as
  in MIT 18.S096 Lecture 7: historical simulation on 500 days of real joint
  returns, variance-covariance on a Ledoit-Wolf shrinkage covariance
  (Lecture 10), and 10,000 correlated Monte Carlo draws through a Cholesky
  factor. Adds expected shortfall, each position's share of the risk, and a
  Kupiec backtest of whether the VaR broke as often as promised. Writes
  mit/var.json, which /mit-risk checks against max_var_pct. Use when the
  user asks "how much could I lose", "what's my risk", "VaR", "worst case",
  "expected shortfall", "is my portfolio too risky", or before /mit-risk.
argument-hint: "[--include-orders]"
---

# mit-var

One number for the whole account: the 1-day loss you should exceed only one
day in a hundred. And, because that day will come, the average loss on such
days (expected shortfall).

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/var.py" run --include-orders --write     # holdings + the orders waiting
python3 "${CLAUDE_SKILL_DIR}/var.py" run --conf 0.95
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/portfolio.json` | cash and positions (`symbol`, `qty`) |
| `mit/orders.json` | with `--include-orders`: added as if filled |
| `mit/config.json` | `var_confidence`, `max_var_pct` |
| `mit/var.json` | the result; /mit-risk blocks an order whose VaR is over `max_var_pct` of equity |

## The math (L7, L10, L2)

- **Historical:** today's positions x each of the last 500 days' real returns
  (all assets on the same day, so correlations are real). VaR = the 99th
  percentile loss.
- **Parametric:** loss sd = sqrt(v' S v) for dollar positions v and covariance S
  (Ledoit-Wolf shrinkage), VaR = 2.33 x sd. Expected shortfall = sd x
  phi(z) / (1 - 0.99).
- **Monte Carlo:** correlated normal returns r = L e with S = L L' (Cholesky).
- **Kupiec test:** over the last 250 days, each day's historical VaR from the
  days before it. About 2.5 breaks are expected; the likelihood-ratio test
  says whether the count is believable.
- The worst of the three, as a percent of equity, is what /mit-risk checks.

## Steps

1. `var.py run --include-orders --write` after /mit-portfolio.
2. Say the VaR and expected shortfall in dollars and as a percent of equity,
   which position carries most of the risk, and the Kupiec result.
3. Next: /mit-risk.

## Example: NVDA order, November 20, 2026, $10,000 account

```
  equity $10,000.00, gross exposure $753.18 (includes 1 proposed order(s))
  1-day VaR: historical $58.85, parametric $50.88, Monte Carlo $49.39
  expected shortfall (average loss beyond the VaR): historical $86.48, parametric $58.30
  Kupiec backtest: 2 of the last 250 days lost more than the VaR (expected 2.5), p = 0.742: the model holds up
  worst of the three: 0.59% of equity; your limit is 5.0%: within it
```

The historical expected shortfall ($86) is well above the normal model's
($58): NVDA's real tails are fatter than a bell curve.

## Rules

- VaR is not the worst case. Say that every time. Expected shortfall is closer.

## Safety

- Education and tooling, not financial advice. Nothing here places an order.
