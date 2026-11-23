---
name: mit-portfolio
description: >-
  Position Sizer and Allocator. Turns trade plans into orders sized by the
  Kelly criterion from the Monte Carlo odds (MIT 18.S096 Lectures 16 and 25;
  half Kelly by default), capped by the user's max loss per trade, position
  size, order size and cash buffer; Kelly at or below zero means no order.
  Also builds long-term allocations (risk parity, minimum variance, capped
  mean-variance; Lectures 14 and 16, Case Study 6) on a Ledoit-Wolf
  shrinkage covariance (Lecture 10). Writes mit/orders.json and
  mit/targets.json. Use when the user asks "how much should I buy", "size
  this trade", "Kelly", "position size", "build me a portfolio", "risk
  parity", "how should I split my money", or after /mit-montecarlo.
argument-hint: "[size | optimize]"
---

# mit-portfolio

Two questions: how big should this one trade be, and how should money be
split across assets for the long run.

`${CLAUDE_SKILL_DIR}` below is this skill's folder. Copy
`${CLAUDE_SKILL_DIR}/config.example.json` to `mit/config.json` and edit it:
it holds the budget and every limit the pack uses.

```bash
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" size --write                    # Kelly
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" size --method fixed --write     # risk exactly your max loss
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" optimize --tickers SPY,QQQ,TLT,GLD,IEF,XLE --method riskparity
python3 "${CLAUDE_SKILL_DIR}/portfolio.py" optimize --tickers SPY,TLT,GLD --method minvar --cap 0.30 --write
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/plan.json` | plans with Monte Carlo odds |
| `mit/config.json` | budget, kelly_fraction, max_loss_per_trade_usd, max_position_pct, max_order_usd, cash_buffer_pct, fractional |
| `mit/portfolio.json` | cash and positions; if missing, a fresh account funded with the budget |
| `mit/orders.json` | the sized orders (brackets for stocks; simple orders for crypto) |
| `mit/targets.json` | `optimize --write`: target weights |

## Sizing (L16, L25)

- The Monte Carlo gives the outcome of each path in R (units of the amount at
  risk). The growth-optimal fraction of capital to risk is f = E[R] / E[R^2].
- Full Kelly is famously aggressive. The pack bets `kelly_fraction` of it
  (0.5 = half Kelly): about 3/4 of the growth with half the swings.
- Hard limits always win: risk at most `max_loss_per_trade_usd`; then position,
  order size and cash caps. Whole shares for stocks; crypto to 6 decimals.
- f <= 0 or an edge inside the simulation noise: no order. Say so. `--method
  fixed` sizes to the max loss anyway; only use it when the user asks.
- Pairs: the size is dollars of the first leg; the second leg is hedge ratio x
  that, sold short (blocked by /mit-risk unless `allow_short`).

## Allocation (L10, L14, L16)

- Covariance by Ledoit-Wolf shrinkage toward a scaled identity: the sample
  covariance of many assets is noisy, and optimizers chase the noise.
- riskparity: each asset adds the same share of risk. minvar: lowest
  variance with a cap per asset (Case Study 6 uses 30%). meanvar: Markowitz with
  past means shrunk halfway to their average, capped.
- These are long-term targets, not trade signals.

## Example: NVDA, November 20, 2026, $10,000 account

```
  NVDA: no order
      - Kelly: full 0.00% of capital at risk, x 0.5 = 0.00% ($0.00)
      - Kelly says do not bet: the simulated odds do not pay for the risk
```

With `--method fixed` (the user insisted): 6 shares ($753.18), max loss at
the stop $96.60, under the $100 limit.

## Rules

- Never raise a limit or loosen a stop to make an order bigger.
- Show the arithmetic: risk per share, shares, dollars, max loss.

## Safety

- Education and tooling, not financial advice.
- Nothing here places an order. Only /mit-broker can lead to one, after /mit-risk and the user's yes.
