<!-- Reviewed for local use -->
# Monte Carlo odds (montecarlo.py)

Before risking a dollar, play the trade forward many times and count.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/montecarlo.py" run --write               # every plan in mit/plan.json
python3 "${CLAUDE_SKILL_DIR}/scripts/montecarlo.py" run NVDA --model gbm
python3 "${CLAUDE_SKILL_DIR}/scripts/montecarlo.py" run NVDA --drift zero      # assume no edge at all
python3 "${CLAUDE_SKILL_DIR}/scripts/montecarlo.py" run NVDA --paths 50000 --seed 7
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/plan.json` | the plans; it writes `montecarlo`, `history` and `odds_verdict` into each |
| `mit/signals.json` | the measured edge that sets the drift |
| `mit/bars/` | the price history |

## The math

- **The drift, and why it matters most (L5).** With no edge, a price is a
  martingale. Doob's optional stopping theorem then says no stop/target rule
  can change the expected result: it is exactly zero. Stops and targets
  change the shape of the outcomes, never their average. So the only drift
  simulated is **signal**'s measured excess return, multiplied by its
  credibility = t / (the bar for luck), between 0 and 1. A NONE setup gets
  about zero.
- **garch (default, L7, L9):** each day's variance from the fitted GARCH; each
  day's shock drawn from the stock's own past standardized returns, so the
  tails are as fat as they really were.
- **gbm (L18):** dS/S = mu dt + sigma dW. By Ito's lemma the log price drifts by
  mu - sigma^2/2 a day.
- **bootstrap:** past daily returns drawn at random, de-meaned.
- **ou (pairs, L21):** dX = kappa (theta - X) dt + sigma dW, simulated exactly.
- **Brownian bridge (L17):** a path from x0 to x1 touched barrier b in between
  with probability exp(-2 (x0 - b)(x1 - b) / variance). Daily steps still catch
  intraday stops.
- **Kelly (L16, L25):** the fraction of capital to risk that maximizes long-run
  growth, f = E[R] / E[R^2], R in units of the amount at risk. Set to 0 when
  E[R] is within 2 standard errors of the simulation: an edge inside the
  noise is no edge.
- **History:** every past day the setup fired (at least h days apart), stop and
  target set the same way from that day's EWMA vol, outcome on closes.

## Steps

1. `montecarlo.py run --write`.
2. Tell the user: target first, stop first, neither; the expected result in R
   with its margin of error; the drift and where it came from; the 5%, 50%,
   95% price range; the history counts; the verdict.
3. If the verdict is "close to a coin flip", say so plainly. That is the point
   of looking before risking money.
4. Next: `**portfolio** size`.

## Example: NVDA, November 20, 2026 (real data)

```
buy NVDA dip: entry 125.53, stop 109.43, target 165.18, 5 days
  10,000 paths (garch model, seed 18): target first 3.8%, stop first 28.5%, neither by day 5 67.7%
  drift: **signal**: +1.11% excess per 5 days x credibility 0.22 (t 0.79 / bar 3.62)
  expected result +0.015 R (+/- 0.019; R = the amount at risk); growth-optimal Kelly risk fraction 0.0%
  price in 5 days: 5% chance below 104.68, median 124.32, 5% chance above 153.82
  history 2021-11-22 to 2026-11-20: the rule fired 26 times; 2 hit the target, 5 the stop, 19 neither
  verdict: close to a coin flip.
```

## Rules

- A simulation, not a prediction. The future can do what the past never did.
- Always report the seed, so anyone can repeat the numbers.

## Safety

- Education and tooling, not financial advice.
- Nothing here places an order. Only **broker** can lead to one, after **risk** and the user's yes.
