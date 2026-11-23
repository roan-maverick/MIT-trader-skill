# Risk gate (check.py)

Every order passes through here. A BLOCK is final for that order: it is not
shown to the user for a yes and it never reaches the broker. These limits
keep each loss and each day's losses small. They do not make a trade win.

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check.py"                           # writes mit/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/scripts/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/scripts/check.py" --no-write                # look without recording
python3 "${CLAUDE_SKILL_DIR}/scripts/check.py" --now "2026-11-23 10:00"  # pin the clock (New York time)
```

## What it reads and writes

| file | what |
| --- | --- |
| `mit/orders.json` | the proposed orders |
| `mit/config.json` | the limits (`config.example.json` in the skill folder shows them all) |
| `mit/portfolio.json` | cash and holdings; if missing, a fresh account funded with the budget |
| `mit/var.json` | the account's VaR with the orders in it (**var**) |
| `mit/signals.json` | **signal**'s verdicts |
| `mit/prices.json` | a price under 15 minutes old raises the entry it measures risk from |
| `mit/state/broker.json` | what was placed today: duplicates, trades, the day's risk |
| `mit/state/risk.json` | the verdicts it writes, with a fingerprint of each exact order |

## The checks

Orders are checked in file order, as if each passed order had filled.

| check | blocks an entry when |
| --- | --- |
| format | no symbol, bad side or qty, fractional shares while `fractional` is false, a bracket without both legs or not day/gtc, a bracket on crypto |
| asset | options while `allow_options` is false, crypto while `allow_crypto` is false, anything not a US ticker or supported coin |
| short | a sell of more than you hold while `allow_short` is false (always blocks) |
| stop | no stop while `require_stop` is true; a stop on the wrong side |
| loss | qty x (entry - stop) over `max_loss_per_trade_usd` |
| reward:risk | (target - entry) / (entry - stop) under `min_reward_risk` |
| daily loss | the max losses of today's entries plus this one over `max_daily_loss_usd` |
| trades / daily limit | `max_trades_per_day` entries or `max_orders_per_day` orders already today |
| size / position / cash | under `min_order_usd`, over `max_order_usd`, over `max_position_pct` of equity, more than cash minus the `cash_buffer_pct` buffer |
| window | a stock order while the market is closed (weekends, NYSE holidays to 2027), before `no_entries_before` or after `no_entries_after` (New York time). Crypto is never blocked by the clock |
| VaR | the 1-day VaR in mit/var.json, with this order in it, over `max_var_pct` of equity |
| edge | **signal** rated the setup NONE or WEAK, only while `require_edge` is true (otherwise a warning) |
| duplicate / blocked | same symbol and side twice today; a ticker on `blocked` |

An **exit** (a sell of what you hold, or a buy that covers a short) is
checked for format, asset and short only. Everything else becomes a warning:
getting out must always be possible.

Warnings to say out loud: no proven edge, no VaR yet, a crypto stop that lives
only in the plan, a LIVE account, an early close.

## Steps

1. Run `check.py`. Exit code 0: all passed. 1: at least one blocked.
2. Tell the user order by order: the max loss at the stop, reward:risk, how
   much of today's limits it uses, and every warning. For a BLOCK give the
   reason and the honest fix (fewer shares, wait for the window, or skip it).
   Never change a limit yourself.
3. If an order changes in any way, run it again: **broker** matches orders to
   verdicts by fingerprint, and a verdict from another day does not count.

## Example: NVDA, Monday November 23, 2026, 10:00 New York

```
PASS  #1 buy NVDA 6, entry
          entry 125.53, stop 109.43, target 165.18: max loss $96.60 (limit $100.00), reward:risk 2.46 (min 1.5)
        ! **signal** rated this setup NONE: no proven edge
```

7 shares: BLOCK, `loss: $112.70 at the stop, over your $100.00 max loss per trade`.
At 9:40: BLOCK, `window: before 09:45 New York`. On Sunday: BLOCK, `the stock market is closed (weekend)`.

## What it never does

It never places an order, never edits an order to make it pass, never
loosens a limit, never blocks a sell that only gets the user out, and never
treats a PASS as the user's yes.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except through **broker**, and only when all three hold: **risk**
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card (the order tool set to "Needs approval").
- No options, margin or short selling unless the config allows it and the user confirms.
