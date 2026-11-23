---
name: mit-factors
description: >-
  Factor Analyst. Splits a stock's returns into the part that is just the
  market and the part that is its own, with MIT 18.S096's factor models:
  CAPM beta and alpha with t-stats (Lecture 6, Case Study 1), a Kalman-filter
  beta that changes over time (Lecture 12), a macro factor model on ETFs
  (market, small caps, tech, bonds, gold, energy; Lecture 15) and principal
  components of a whole universe (Lectures 2 and 15) with the random-matrix
  noise edge. Use when the user asks "what's the beta", "is this alpha",
  "is it just the market", "what drives this stock", "factor exposure",
  "PCA", "how correlated is my portfolio", or before sizing a trade.
argument-hint: "[symbol]"
---

# mit-factors

"NVDA fell 14% today" means little until you know how much of that was the
market. Beta answers that; alpha is what is left, and it is usually not
statistically different from zero.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/factors.py" beta NVDA [--bench QQQ] [--window 252] [--write]
python3 "${CLAUDE_SKILL_DIR}/factors.py" model NVDA [--write]
python3 "${CLAUDE_SKILL_DIR}/factors.py" pca [--tickers AAPL,MSFT,NVDA,JPM,XLE,TLT,GLD]
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/bars/` | price history (it needs SPY, IWM, QQQ, TLT, GLD, XLE for `model`) |
| `mit/factors.json` | with `--write`: the beta or model per symbol |

## The math

- **CAPM (L1, L6, Case Study 1):** r_stock = alpha + beta r_market + e by OLS.
  R^2 is the market's share of the stock's variance. Alpha is annualized x 252
  with its t-statistic: |t| under 2 means it cannot be told apart from zero.
- **Time-varying beta (L12):** a linear state-space model, (alpha_t, beta_t) a
  random walk, estimated by the Kalman filter one day at a time.
- **Macro factor model (L15):** time-series regression on factor returns built
  from ETFs: market = SPY, small caps = IWM - SPY, tech = QQQ - SPY,
  long bonds = TLT, gold = GLD, energy = XLE.
- **PCA (L2, L15):** eigenvectors of the correlation matrix of returns (Jacobi
  method). The first component is usually "the market". Eigenvalues above the
  Marchenko-Pastur edge (1 + sqrt(N/T))^2 are real structure; below it,
  noise.

## Steps

1. `factors.py beta SYMBOL`. Say the beta in plain words ("a 1% move in the
   S&P comes with about 1.9% in NVDA"), the R^2 and whether the alpha is real.
2. For a trade: a high beta means the trade is partly a bet on the market;
   /mit-var will show it.
3. `pca` for a portfolio: how many independent bets it really holds.

## Example: NVDA, November 20, 2026 (real data)

```
NVDA vs SPY, 252 daily returns to 2026-11-20
  beta 1.93 (t 14.1): a 1% move in SPY comes with 1.93% in NVDA on average
  Kalman beta now 1.77 (60 days ago 1.82)
  R^2 44%: that share of its daily variance is the market; the rest is its own
  alpha -49.2% a year, t = -1.58, p = 0.12: not distinguishable from zero
```

PCA of 41 symbols that day: the first component explained 29% of the
variance, and 5 eigenvalues were above the noise edge.

## Safety

- Education and tooling, not financial advice. Nothing here places an order.
