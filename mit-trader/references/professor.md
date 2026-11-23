<!-- Reviewed for local use -->
# The Professor (the course)

The pack's teacher. The other skills compute; this one explains why the
computation is right, where it comes from, and where it breaks.

The notes are in `${CLAUDE_SKILL_DIR}/references/lectures/`, one file per lecture
(`L01.md` to `L26.md`). Read only the ones the question needs.

## The course map

| # | lecture | used by |
| --- | --- | --- |
| 1 | Introduction, financial terms and concepts | all; alpha and beta in **factors** |
| 2 | Linear algebra: eigenvalues, SVD, Perron-Frobenius | **factors** pca, **var** (Cholesky) |
| 3 | Probability: normal, lognormal, LLN, CLT | **scan** z-scores, **signal** |
| 4 | Matrix primer (no published notes) | **factors**, **var** |
| 5 | Stochastic processes I: random walks, Markov chains, martingales, optional stopping | **montecarlo** (drift rule) |
| 6 | Regression analysis | **signal**, **factors**, **scan** trend |
| 7 | Value at Risk | **var** |
| 8 | Time series I: stationarity, ARMA, unit roots | **scan**, **pairs** |
| 9 | Volatility modeling: GBM, GARCH | **vol**, **montecarlo** |
| 10 | Regularized pricing and risk models | **portfolio**, **var** (shrinkage) |
| 11 | Time series II: VAR models | **pairs** |
| 12 | Time series III: cointegration, state space, Kalman | **pairs**, **factors** |
| 13 | Commodity models | background |
| 14 | Portfolio theory: Markowitz | **portfolio** optimize |
| 15 | Factor modeling: CAPM, macro factors, PCA | **factors** |
| 16 | Portfolio management: Sharpe, Kelly, risk parity | **portfolio** |
| 17 | Stochastic processes II: Brownian motion | **montecarlo** (bridge) |
| 18 | Ito calculus, Girsanov | **montecarlo** gbm, **options** |
| 19 | Black-Scholes, risk-neutral valuation | **options** |
| 20 | Option price and probability duality | **options** prob, chain |
| 21 | Stochastic differential equations: OU, Monte Carlo, trees | **pairs**, **montecarlo** |
| 22 | Calculus of variations in FX execution (no published notes) | **execution** |
| 23 | Quanto credit hedging | background |
| 24 | HJM model for rates and credit | background |
| 25 | Ross recovery theorem | **options** (risk-neutral vs real), Kelly |
| 26 | Counterparty credit risk, conclusions | background, **risk** philosophy |

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
