# Volatility and exit planner (vol.py)

Volatility is not constant: calm days follow calm days and wild days follow
wild days. GARCH(1,1) captures that with three numbers and turns the latest
shocks into a forecast. A stop closer than one forecast standard deviation
is likely to be hit by noise alone.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" fit NVDA
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" plan NVDA --setup dip --write
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" plan NVDA --stop-sigma 1.5 --target-sigma 3 --write
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" plan NVDA --target mean --write        # target = the 20-day mean
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" plan --from-candidates --top 3 --write --replace
python3 "${CLAUDE_SKILL_DIR}/scripts/vol.py" plan --from-candidates --only-edge --write
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/config.json` | `horizon_days`, `stop_sigma`, `target_sigma`, `allow_short` |
| `mit/candidates.json`, `mit/signals.json` | for `--from-candidates` (EDGE first, then WEAK, then the rest) |
| `mit/plan.json` | the plans: entry, stop, target, horizon, the GARCH fit |

## The math (L9)

sigma^2(t) = omega + alpha r^2(t-1) + beta sigma^2(t-1)

- alpha: how hard volatility reacts to yesterday's move. beta: how long it
  remembers. alpha + beta (persistence) near 1: shocks fade slowly; the
  half-life of a shock is ln(0.5) / ln(alpha + beta) days.
- All three are fitted by maximizing the Gaussian likelihood (Nelder-Mead).
- The h-day forecast adds the daily forecasts, which decay toward the
  long-run variance omega / (1 - alpha - beta).
- Fat tails: excess kurtosis (0 for a normal). Clustering: a Ljung-Box test on
  squared returns (the ARCH effect).

The plan: stop = entry x exp(-k_stop x sigma_h), target = entry x exp(k_target x sigma_h)
for a buy (mirrored for a short). Prices are rounded to cents.

## Steps

1. `vol.py fit SYMBOL`. Tell the user tomorrow's forecast vs the long-run
   level and what one standard deviation over the horizon means in dollars.
2. `vol.py plan SYMBOL --write`. Say the stop, the target, the amount at risk
   per share and reward:risk.
3. Next: `**montecarlo** run` for the odds of the plan.

## Example: NVDA, November 20, 2026 (real data)

```
  GARCH(1,1): alpha 0.121 (reaction to news), beta 0.841 (memory), persistence 0.962, a shock halves in 18.0 days
  annualized vol: tomorrow 100.0%, long-run 55.7%, EWMA 78.0%, last 20 days 69.0%
  next 5 days: one standard deviation is 13.72% (move of $17.23 on 125.53)
  fat tails: excess kurtosis 4.97 (normal = 0), skew -0.25
Plan: buy NVDA at 125.53 (dip setup, 5-day horizon)
  stop   109.43  (1.0 sigma of the 5-day GARCH vol 13.72%: 16.10 a unit at risk)
  target 165.18  (2.0 sigma: 39.65 a unit)  reward:risk 2.46
```

After a 14% one-day drop, GARCH expects tomorrow to be about twice as wild
as normal. A stop at a "normal" 5% would very likely be hit by noise.

## Rules

- Never move a stop closer to make a position bigger. Size comes from **portfolio**.
- A stop is a plan, not a guarantee: across a gap it can fill well past its price.

## Safety

- Education and tooling, not financial advice.
- Nothing here places an order. Only **broker** can lead to one, after **risk** and the user's yes.
