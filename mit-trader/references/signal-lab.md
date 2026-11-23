# Signal Lab (signal.py)

The most important skill in the pack, because it is the one that says no.
Almost every pattern looks good in a chart. This asks the history.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/signal.py" candidates --write            # every setup in mit/candidates.json
python3 "${CLAUDE_SKILL_DIR}/scripts/signal.py" test NVDA --setup dip --n-tests 168 --write
python3 "${CLAUDE_SKILL_DIR}/scripts/signal.py" test BTC --setup trend --horizon 10
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/candidates.json` | the setups and `n_tests` from **scan** |
| `mit/config.json` | `horizon_days` (5 by default) |
| `mit/signals.json` | one result per symbol and setup, with the verdict |

## The three tests (L6, L8)

1. **Predictive regression.** r(t, t+h) = a + b x signal(t) + e over about 5
   years of days. h-day returns sampled daily overlap, so ordinary standard
   errors are too small; it uses Newey-West (HAC) errors with h-1 lags.
2. **Event study.** Every past day the rule fired, at least h days apart so
   one episode is not counted five times. The h-day return after each,
   minus an ordinary h-day return, its average, win rate and t-statistic.
3. **Out of sample.** The history is split 70/30 by date. The edge must
   still be there in the last 30%.

**The bar for luck.** If the scanner ran N tests, the chance that at least
one clears |t| = 2 by luck is high. The bar is the Bonferroni value
z(1 - 0.05 / 2N): 1.96 for one test, 3.62 for 168.

**Verdict.** EDGE: the event study or the regression clears the bar AND the
out-of-sample excess is positive. WEAK: leans the right way (t of 1 or more)
but does not clear the bar. NONE: no evidence.

## Steps

1. `signal.py candidates --write` after the scanner (or `test` for one).
2. Report each verdict in plain words with its numbers: how many events, what
   followed on average, the win rate, the t-statistic and the bar.
3. Be blunt about NONE and WEAK. A 69% win rate on 26 events can be luck.
4. Next: `**vol** plan` for anything the user still wants to look at.
   **montecarlo** will use only this skill's measured edge, shrunk by
   credibility = t / bar, as drift.

## Example: NVDA dip, November 20, 2026 (real data)

```
NVDA dip, 5-day horizon, 2021-11-22 to 2026-11-20 (1255 days)
  signal now -2.29 (fires)
  past events: 26. After them the 5-day return averaged 1.76% (an ordinary 5 days: 0.65%), won 69% of the time, t = 0.79
  predictive regression: t = 0.28 (Newey-West), R^2 = 0.0002
  out of sample (after 2025-05-28): 9 events, excess 2.40% vs 0.42% before
  bar for luck: |t| >= 3.62 (168 tests today)
  verdict NONE: no evidence this setup pays. Treat it as a coin flip or worse.
```

Across all 32 setups that day: 0 EDGE, 7 WEAK, 25 NONE. That is a normal day.

## Rules

- Never round a WEAK up to an EDGE, and never describe a NONE as promising.
- Past performance is a sample, not a law. Say so when a verdict is EDGE.

## Safety

- Education and tooling, not financial advice.
- Nothing here places an order. Only **broker** can lead to one, after **risk** and the user's yes.
