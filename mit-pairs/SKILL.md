---
name: mit-pairs
description: >-
  Pairs Trader. Statistical arbitrage on two assets that move together, with
  MIT 18.S096's cointegration (Lectures 11 and 12): an Engle-Granger test
  (log-price regression, then an ADF unit-root test on the spread with
  MacKinnon critical values), the spread's Ornstein-Uhlenbeck half-life
  (Lecture 21), its z-score now, and a Kalman-filter hedge ratio. Scans
  pairs within sector groups (megacaps, semis, chip equipment, banks,
  staples, energy, gold, bonds, indexes, crypto) and says how many would
  pass by luck alone. Writes a two-leg plan that /mit-montecarlo simulates as
  an OU process. Use when the user asks about "pairs trading", "stat arb",
  "cointegration", "spread trade", "GLD vs GDX", "long one short the other",
  "market neutral", or "mean reversion between two stocks".
argument-hint: "[symbol A] [symbol B]"
---

# mit-pairs

Two prices can each wander like random walks and still be tied together, so
that a combination of them keeps coming back. When that tie is real, a
stretched spread is a bet on it snapping back, mostly independent of the
market. When it is not real, the spread can stretch forever.

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/pairs.py" scan [--groups semis,banks,gold] [--write]
python3 "${CLAUDE_SKILL_DIR}/pairs.py" test GLD GDX
python3 "${CLAUDE_SKILL_DIR}/pairs.py" plan LRCX KLAC [--entry-z 2] [--stop-z 1.5] --write
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/bars/` | price history |
| `mit/pairs.json` | `scan --write`: cointegrated pairs and the ones stretched now |
| `mit/plan.json` | `plan --write`: the pair plan (legs, hedge ratio, spread z, OU fit, risk per $1) |

## The math

1. **Cointegration (L12).** log A = a + beta log B + spread, by OLS. If A and B
   each wander (I(1)) but the spread does not (I(0)), they are cointegrated.
   The lecture's examples include the law of one price for equivalent assets.
2. **Engle-Granger test (L8, L12).** An ADF test on the spread. Because beta was
   fitted, ordinary ADF critical values are too lenient; it uses MacKinnon's
   Engle-Granger values (about -3.34 at 5% for two assets).
3. **OU half-life (L21).** The spread's AR(1) coefficient phi gives kappa =
   -ln(phi) a day and a half-life of ln 2 / kappa days.
4. **z-score.** How many standard deviations the spread is from its mean today.
   The plan buys the spread (long A, short beta dollars of B) when z <= -2,
   sells it when z >= 2, targets z = 0, stops 1.5 further out, and gives up
   after about two half-lives.
5. **Kalman hedge ratio (L12).** beta changes over time; the filter tracks it.
6. **Luck.** A scan tests many pairs. At the 5% level, 1 in 20 unrelated pairs
   "passes". The scan prints how many would pass by luck alone.

## Steps

1. `pairs.py scan`. Report how many pairs passed vs how many luck alone would
   pass, then any stretched ones.
2. `pairs.py test A B` for one pair: hedge ratio, ADF vs the 5% value,
   half-life, z now.
3. `pairs.py plan A B --write`, then `/mit-montecarlo run A`, `/mit-portfolio size`.
4. A pair needs a short sale. /mit-risk blocks it unless the user sets
   `allow_short` to true and their broker account allows shorting.

## Example: November 20, 2026 (real data)

```
Tested 56 pairs within 10 groups. Cointegrated at 5%: 2. By luck alone about 3 would pass.
  SOXX     vs INTC     hedge  0.55  ADF  -3.81 (5%: -3.36) cointegrated: yes, 5% level half-life   7.9 d  z now +0.36
  LRCX     vs KLAC     hedge  1.15  ADF  -3.46 (5%: -3.36) cointegrated: yes, 5% level half-life   9.4 d  z now -0.23
Stretched now (|z| >= 2, half-life <= 30 days): 0
```

Two passes where luck alone predicts three: no evidence of real pairs that
day. GLD vs GDX, the textbook pair: ADF -1.66, not cointegrated over the year.

## Safety

- Education and tooling, not financial advice. Short selling can lose more than was put in.
- Nothing here places an order. Only /mit-broker can lead to one, after /mit-risk and the user's yes.
