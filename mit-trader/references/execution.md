<!-- Reviewed for local use -->
# Execution planner (execution.py)

For most personal orders the answer is "one market order is fine". For a
big order, how you trade it costs real money.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/execution.py" plan NVDA --qty 5000000 --adv 250000000 --urgency 1
python3 "${CLAUDE_SKILL_DIR}/scripts/execution.py" plan BTC --qty 50 --hours 24 --slices 24 --urgency 0.5
python3 "${CLAUDE_SKILL_DIR}/scripts/execution.py" plan --from-orders --write
```

`--adv` is the average daily volume in shares (or coins). Live Yahoo data
includes volume, so it is only needed when the data has none.

## The math (L22)

You must trade X over time T. Holdings x(t) go from X to 0.

- Trading fast costs temporary impact, about eta x (speed)^2 in total.
- Trading slowly leaves the position exposed: variance sigma^2 times the
  integral of x(t)^2.
- Minimize cost + lambda x variance over every path x(t): a calculus of
  variations problem. The Euler-Lagrange equation is x'' = kappa^2 x with
  kappa^2 = lambda sigma^2 / eta, solved by x(t) = X sinh(kappa(T-t)) / sinh(kappa T).
- kappa = 0 is a straight line (TWAP). The tool takes urgency = kappa T: 0 even,
  1 leaning early, 3 or more front-loaded.
- Impact is scaled so that trading 10% of a day's volume in a day costs about
  0.1 daily standard deviations per share; under 0.5% of a day's volume it
  says one order is fine. The lecture's own materials were not published
  (no notes or video on OCW for Lecture 22); the model here is the standard
  one for this problem.

## Example

6 NVDA shares: `Small next to the market: one order is fine.` 5,000,000
shares (2% of 250M a day) over 6.5 hours in 6 slices: urgency 0 gives
833,333 every 65 minutes; urgency 3 gives 1,971,475 first, then 1,207,982,
749,021 and less, at a higher expected cost but a much smaller spread of
outcomes.

## Safety

- Education and tooling, not financial advice. It plans; it never places an order.
- Each slice is its own order: it goes through **risk** and the user's own yes in **broker**.
