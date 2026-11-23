<!-- Reviewed for local use -->
# Strategy hunter (hunt.py): the overnight research

Hunts for trading rules that really paid, with the statistics of the course,
and writes the survivors to `mit/strategies.json`: the bot's playbook.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/hunt.py" run --write                 # the universe in mit/config.json, 10 years
python3 "${CLAUDE_SKILL_DIR}/scripts/hunt.py" run --tickers SPY,QQQ,BTC,ETH,NVDA --write
python3 "${CLAUDE_SKILL_DIR}/scripts/hunt.py" run --cost-bps 5 --fdr 0.05 --write
python3 "${CLAUDE_SKILL_DIR}/scripts/hunt.py" show                        # the playbook
python3 "${CLAUDE_SKILL_DIR}/scripts/hunt.py" today --write               # approved rules firing today -> mit/candidates.json
```

`autopilot.py research` runs `hunt.py run --write` and says what the bot will
trade. A live run on 40+ symbols takes a few minutes (most of it downloading);
that is why it is the overnight job.

## The rule library (51 variants)

| family | rule | lectures |
| --- | --- | --- |
| dip | close 1.5 / 2 / 2.5 std below its 10 / 20 / 50-day mean (buy) | L3, L8 mean reversion |
| rip | close 2 / 2.5 std above its 20-day mean (short) | L3, L8 |
| trend | 63 / 126-day log-price trend with t >= 2 / 3 (buy) | L6 regression |
| breakout | close at a new 252-day high (buy) | L5, L17 (running maximum) |
| calm | above the 200-day mean while 20-day vol < 0.8 x 1-year vol (buy) | L9 volatility regimes |

Each is held 5, 10 or 21 trading days. To add an idea, edit `library()` and
`fire_series()` in `hunt.py`: every new variant raises the bar for all of them.

## How a rule is judged

1. **Pooled event study (L6).** On every symbol, every day the rule fired (at
   least one holding period apart): the h-day log return in the trade's
   direction, minus that symbol's ordinary h-day return, minus a round trip of
   trading costs (10 bps a side by default). That is the rule's excess per trade.
2. **Clustered by week.** A market-wide selloff fires a dip rule on 40 stocks
   at once; those trades are one bet, not 40. Excess returns are averaged per
   entry week, and the t-statistic is taken over weeks.
3. **Walk-forward.** The first 70% of the history (by date) is in-sample. The
   last 30% is out-of-sample and plays no part in the discovery.
4. **Multiple testing.** One-sided p-values from the in-sample t-statistics go
   through Benjamini-Hochberg at a 10% false discovery rate (at most about 1 in
   10 discoveries is luck). The stricter Bonferroni bar is reported too.
5. **APPROVED** = a BH discovery with at least 30 in-sample trades, AND at least
   10 out-of-sample trades with positive excess and t >= 1. A discovery that
   fails out of sample is marked FAILED OUT OF SAMPLE: the classic overfit.

The edge the bot simulates for an approved rule: its out-of-sample excess per
trade x credibility (in-sample t / Bonferroni bar, capped at 1).

## Steps

1. `autopilot.py research` (or `hunt.py run --write`).
2. Tell the user: how many variants, how many approved, and for each approved
   rule its excess per trade in and out of sample, t-statistics, trade counts and
   win rate. Then the closest calls that failed, and why (usually: good
   in-sample, nothing out of sample).
3. If none is approved, say plainly that the bot will stand down, and why that
   is the right answer.
4. Offer to schedule it nightly and `autopilot.py run` each morning.

## Example: real data to November 20, 2026

138 US stocks and ETFs plus Bitcoin, November 2016 to November 2026
(`tests/fixtures/universe-10y.json.gz`), split at 2024-05-08:

```
51 rule variants tested. Cost 10.0 bps a side. Benjamini-Hochberg false discovery rate 0.1; Bonferroni bar t >= 3.096.

## Approved: 0
| dip-w20-zm1.5-h5  | REJECTED | +0.35% | 2.15 | +0.00% | 0.02 |
| dip-w10-zm1.5-h5  | REJECTED | +0.34% | 2.15 | +0.09% | 0.39 |
| dip-w10-zm1.5-h10 | REJECTED | +0.47% | 2.11 | -0.11% | -0.29 |
```

Buying dips looked like +0.35% a trade for seven and a half years, then made
nothing once the rule had to work on data it had not seen. A backtest that
stops at the in-sample number would have sold you that rule. The bot stands down.

On a test market with a real edge planted in it (`tests/test_hunt.py`), the same
hunt approves the dip rules (in-sample t about 15, out-of-sample t about 10) and
the bot turns them into sized, risk-checked tickets. The machinery finds edges
when they exist; it does not invent them.

## Safety

- Education and tooling, not financial advice. A rule that paid in the past can stop paying.
- Nothing here places an order. Only the broker step can, after the risk gate and the user's yes.
