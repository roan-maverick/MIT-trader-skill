<!-- Reviewed for local use -->
# Autopilot (autopilot.py): the trading bot

Research overnight, run the playbook every morning, watch positions around
the clock. It never places an order: it prepares tickets for the user's yes.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" research                 # overnight: hunt.py -> mit/strategies.json
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" run                      # bot mode if a playbook exists
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" run --scan               # ignore the playbook: scan and test everything
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" run --top 5 --method fixed
python3 "${CLAUDE_SKILL_DIR}/scripts/autopilot.py" watch
```

## What `run` does

**Bot mode** (a playbook exists in `mit/strategies.json`):

1. `hunt.py today --write`: which approved rules fire on the latest close, one
   entry per symbol (its strongest rule), with the rule's measured edge.
2. `vol.py plan --from-candidates`: GARCH stop and target over the rule's holding period.
3. `montecarlo.py run`: 10,000 futures, drift = the rule's out-of-sample edge x credibility.
4. `portfolio.py size`: half Kelly, capped by the user's limits.
5. `var.py run --include-orders` and `check.py`: account VaR and the risk gate.
6. `mit/report.md` (and a dated copy in `mit/reports/`).

**Scan mode** (no playbook, or `--scan`): steps 1 is `scan.py run` then
`signal.py candidates`, and the plans go to the setups with the best verdicts.

If no rule is approved, or none fires today, the report says the bot stands
down. Say that plainly; no trade is a fine outcome.

## What `watch` does

Reads `mit/portfolio.json`, fetches the latest price of each position, writes
`mit/prices.json` (the risk gate uses it as a fresh price), and flags any
position past its stop, target or time limit. For crypto (Alpaca has no crypto
brackets) or a passed time limit it writes the closing order to `mit/orders.json`
for the risk gate and the user's yes. Stock stops and targets sit at the broker.

## Scheduling the bot

- **Claude (desktop or web):** offer these scheduled tasks:
  - "Every night at 2:00 AM New York, run the MIT Trader research and tell me what it approved."
  - "Every weekday at 9:50 AM New York, run the MIT Trader bot and send me the report."
  - Crypto: "Every 2 hours, run the MIT Trader watch."
- **Claude Code / cron on the user's machine:**
  `0 2 * * *  cd ~/trading && claude -p "Use the mit-trader skill: autopilot research, then summarize mit/research.md"`
  `50 9 * * 1-5  cd ~/trading && claude -p "Use the mit-trader skill: autopilot run, then summarize mit/report.md"`
- A scheduled run has nobody to say yes, so it can only prepare tickets. By design.

## Steps

1. Run it; read `mit/report.md`.
2. Tell the user in a few lines: the mode, approved rules, symbols firing, the
   odds of what was planned, what was sized, what passed the risk gate.
3. If tickets are READY, show them one at a time with `ticket.py show` (see
   `broker.md`). If not, say no trade is the right outcome today.

## Example: Monday November 23, 2026, 10:00 New York (real data to Nov 20)

Playbook from the research of November 20: 51 variants, 0 approved. Bot mode
reports `approved 0 rule(s), 0 tradeable with your settings (nothing to trade,
so the bot stands down)`. With `--scan`: 32 setups, 0 EDGE; the three WEAK dips
(GDX, MSFT, KLAC) are simulated, Kelly sizes MSFT and KLAC on their small
credibility-shrunk edges and GDX at zero.

## Safety

- Education and tooling, not financial advice. A bot does not change the odds.
- It never places an order. Only the broker step can, after the risk gate passes that exact order
  and the user types yes for it and clicks Allow once.
- Paper trading by default. Run it on paper for weeks before considering anything else.
