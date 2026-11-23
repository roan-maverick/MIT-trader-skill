<!-- Reviewed for local use -->
# Options lab (options.py)

An option price is a probability in disguise. This skill takes the disguise
off.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/options.py" price --spot 125.53 --strike 130 --days 30 --vol 0.65 [--put] [--rate 0.04]
python3 "${CLAUDE_SKILL_DIR}/scripts/options.py" iv --price 9.10 --spot 125.53 --strike 130 --days 30
python3 "${CLAUDE_SKILL_DIR}/scripts/options.py" prob --spot 125.53 --level 150 --days 30 --vol 0.95
python3 "${CLAUDE_SKILL_DIR}/scripts/options.py" chain --file chain.csv --spot 125.53 --days 30
python3 "${CLAUDE_SKILL_DIR}/scripts/options.py" move --spot 125.53 --call 9.10 --put 8.70
```

Chain files are CSV with a `strike` column and either `call` (mid price) or
`bid` and `ask` for calls. The user copies them from their broker; this tool
does not download option chains.

## The math

- **Black-Scholes (L18, L19).** Ito's lemma applied to a hedged portfolio gives
  the PDE; its solution for a call is S N(d1) - K e^(-rT) N(d2). Delta, gamma,
  vega (per vol point), theta (per day) and rho come with it. The check is
  Hull's textbook case: S 42, K 40, 6 months, r 10%, vol 20% gives 4.76.
- **Implied vol.** The vol that makes the formula match the market price (bisection).
- **Duality (L20).** Under the risk-neutral measure, P(S_T > K) = N(d2), and a
  digital call paying $1 above K is worth e^(-rT) N(d2). Calls are prices of
  tails.
- **Breeden-Litzenberger (L20, L25).** The second derivative of call prices in
  the strike is the discounted risk-neutral density: f(K) = e^(rT) d2C/dK2, and
  P(S_T > K) = -e^(rT) dC/dK. A chain becomes the market's distribution, skew and
  fat tails included.
- **Straddle.** An at-the-money straddle costs about E|S_T - S_0|, so one
  standard deviation is about straddle / 0.8 (since E|Z| = sqrt(2/pi)).
- **Risk-neutral is not real-world (L25).** These probabilities include the
  market's fear premium. Ross's recovery theorem tries to strip it out, under
  strong assumptions. Treat them as prices, not forecasts.

## Steps

1. Pick the command for the question and run it.
2. Explain the answer in plain words ("the market prices about a 22% chance
   NVDA is above 150 in 30 days, at 95% implied vol").
3. Say every time that the probabilities are risk-neutral.

## Safety

- Education and tooling, not financial advice. Options can lose 100% of their price quickly.
- This pack does not trade options: `allow_options` is false and **risk** blocks option orders.
