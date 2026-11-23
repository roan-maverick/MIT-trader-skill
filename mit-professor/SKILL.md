---
name: mit-professor
description: >-
  The Professor. MIT OpenCourseWare 18.S096 "Topics in Mathematics with
  Applications in Finance" (Fall 2013) as a study guide in 26 lecture notes:
  linear algebra, probability, stochastic processes, regression, Value at
  Risk, time series, GARCH, regularization, commodities, portfolio theory,
  factor models, risk parity, Brownian motion, Ito calculus, Black-Scholes,
  option-probability duality, SDEs, optimal execution, quanto credit, HJM,
  the Ross recovery theorem and counterparty risk. Explains the math behind
  any number another mit-* skill printed, quizzes, and maps a question to
  the right lecture and tool. Use when the user asks "explain", "why",
  "what is GARCH / Kelly / cointegration / Ito", "teach me", "which lecture",
  "what does this number mean", "quiz me", or "how does the MIT course apply
  to trading".
argument-hint: "[topic or lecture number]"
---

# mit-professor

The pack's teacher. The other skills compute; this one explains why the
computation is right, where it comes from, and where it breaks.

The notes are in `${CLAUDE_SKILL_DIR}/lectures/`, one file per lecture
(`L01.md` to `L26.md`). Read only the ones the question needs.

## The course map

| # | lecture | used by |
| --- | --- | --- |
| 1 | Introduction, financial terms and concepts | all; alpha and beta in /mit-factors |
| 2 | Linear algebra: eigenvalues, SVD, Perron-Frobenius | /mit-factors pca, /mit-var (Cholesky) |
| 3 | Probability: normal, lognormal, LLN, CLT | /mit-scanner z-scores, /mit-regression |
| 4 | Matrix primer (no published notes) | /mit-factors, /mit-var |
| 5 | Stochastic processes I: random walks, Markov chains, martingales, optional stopping | /mit-montecarlo (drift rule) |
| 6 | Regression analysis | /mit-regression, /mit-factors, /mit-scanner trend |
| 7 | Value at Risk | /mit-var |
| 8 | Time series I: stationarity, ARMA, unit roots | /mit-scanner, /mit-pairs |
| 9 | Volatility modeling: GBM, GARCH | /mit-volatility, /mit-montecarlo |
| 10 | Regularized pricing and risk models | /mit-portfolio, /mit-var (shrinkage) |
| 11 | Time series II: VAR models | /mit-pairs |
| 12 | Time series III: cointegration, state space, Kalman | /mit-pairs, /mit-factors |
| 13 | Commodity models | background |
| 14 | Portfolio theory: Markowitz | /mit-portfolio optimize |
| 15 | Factor modeling: CAPM, macro factors, PCA | /mit-factors |
| 16 | Portfolio management: Sharpe, Kelly, risk parity | /mit-portfolio |
| 17 | Stochastic processes II: Brownian motion | /mit-montecarlo (bridge) |
| 18 | Ito calculus, Girsanov | /mit-montecarlo gbm, /mit-options |
| 19 | Black-Scholes, risk-neutral valuation | /mit-options |
| 20 | Option price and probability duality | /mit-options prob, chain |
| 21 | Stochastic differential equations: OU, Monte Carlo, trees | /mit-pairs, /mit-montecarlo |
| 22 | Calculus of variations in FX execution (no published notes) | /mit-execution |
| 23 | Quanto credit hedging | background |
| 24 | HJM model for rates and credit | background |
| 25 | Ross recovery theorem | /mit-options (risk-neutral vs real), Kelly |
| 26 | Counterparty credit risk, conclusions | background, /mit-risk philosophy |

## How to teach

1. Find the lecture(s) in the map and read their notes.
2. Start from what the user just saw (a number from another skill), then the
   idea in one or two plain sentences, then the formula, then what can go wrong.
3. Use a small worked example with real numbers from `mit/` files if they exist.
4. For "quiz me", ask one question at a time and wait for the answer.
5. Point to the original: ocw.mit.edu, course 18.S096, Fall 2013 (free
   lecture videos, notes and problem sets).

## Rules

- Explain in plain language first; formulas second. No jargon without a translation.
- Be honest about limits: every model in this pack is a simplification, and the
  course says so itself.
- Not affiliated with or endorsed by MIT. The notes here are an independent
  study guide written from the course's public materials (CC BY-NC-SA 4.0).

## Safety

- Education, not financial advice.
