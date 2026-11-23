<!-- Reviewed for local use -->
# Broker (ticket.py)

The only skill that can lead to a real order, so the strictest. An order
reaches the market only after three separate gates, every time:

1. ****risk** passed this exact order today** (matched by fingerprint).
2. **The user typed an explicit yes for this one order** in the chat.
3. **The user clicked Allow once** on Claude's own permission card, because the
   order tool is set to "Needs approval".

`${CLAUDE_SKILL_DIR}` is the mit-trader skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" show
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" approve --index 1 --reply "<the user's reply, word for word>"
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" result --index 1 --status placed --broker-id ID --filled-qty 6 --filled-price 125.60
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" fill --symbol NVDA --side sell --qty 6 --price 109.43
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" close --symbol BTC --qty 0.01
python3 "${CLAUDE_SKILL_DIR}/scripts/ticket.py" log
```

`ticket.py` never talks to a broker. It renders tickets, checks that a reply
is a real yes for that order, and keeps the log in `mit/state/broker.json`.
`--now "2026-11-23 10:05"` pins the clock (New York time).

## What it reads and writes

| file | what |
| --- | --- |
| `mit/orders.json` | the orders (**portfolio**, or `close`) |
| `mit/state/risk.json` | **risk**'s verdicts; only a PASS from today, for the same fingerprint, is READY |
| `mit/state/broker.json` | every reply, yes, placement, failure and fill |
| `mit/portfolio.json` | cash and positions, updated by `result --filled-qty` and `fill` (with the plan's stop and target, for **autopilot** watch) |

## Setup: Alpaca (official MCP server, Claude Desktop)

Alpaca's server is github.com/alpacahq/alpaca-mcp-server. It runs on the
user's computer inside Claude Desktop and trades a **paper** account unless
told otherwise.

1. Make an Alpaca account and create **paper trading** API keys in its dashboard.
2. Install `uv` (it provides `uvx`) from docs.astral.sh/uv.
3. Claude Desktop: Settings > Developer > Edit Config. Add the block in
   `claude_desktop_config.example.json` (in the skill folder) and type your own
   paper keys into that file. **Keys never go in the chat.** Never ask for
   them, never read the file back into the conversation. If the user pastes a
   key anyway, tell them to delete the message and make new keys.
4. Restart Claude Desktop.
5. **Tool permissions** (Customize > Connectors > alpaca):
   - `place_stock_order`: **Needs approval**. Never Always allow.
   - `place_crypto_order`: **Needs approval** if the user trades crypto, otherwise Blocked.
   - anything else that places, changes, cancels or closes orders: Needs approval.
   - `place_option_order`, `close_all_positions`, `cancel_all_orders`: Blocked.
   - read-only tools (account, positions, orders, quotes, clock): Always allow is fine.
6. Ask Claude for the Alpaca account info (read only) and confirm in the Alpaca
   dashboard that it is the paper account.

In Claude Code, keep order tools on ask in `.claude/settings.json`:
`"permissions": {"ask": ["mcp__alpaca__place_stock_order", "mcp__alpaca__place_crypto_order"]}`.
Never put an order tool in `allow`.

**Brackets.** Stock orders from **portfolio** are brackets: the entry plus a
stop-loss and a take-profit that wait at the broker and cancel each other
(`take_profit_limit_price`, `stop_loss_stop_price`, gtc). Alpaca has no
brackets for crypto: the stop lives in the plan, and `**autopilot** watch`
must run on a schedule to catch it.

## Steps

1. `ticket.py show`. Only READY tickets go to the user. NOT READY or BLOCKED go
   back to **risk**.
2. Show ONE ticket and ask: "Place this order? Reply yes or no." One order per
   question. Never offer "yes to all".
3. `ticket.py approve --index N --reply "<their reply, word for word>"`. If it
   prints "Not recorded", it was not an explicit yes for this order ("sure",
   "yes to all", a yes naming another stock or amount). Ask again. Never turn
   a reply into a yes yourself.
4. Only after "Recorded your yes", call the tool it names with exactly the JSON
   it printed. Claude's card appears: Allow once or Deny.
5. Record what happened: `result --index N --status placed --broker-id ...
   --filled-qty Q --filled-price P`, or `--status denied`, or `--status failed
   --note ...`. A failed order is not retried without a new check and a new yes.
6. When a stop or target fills, `fill`. To get out, `close`, then **risk**, then
   this flow again. For a stock with an open bracket, cancel its legs first
   (get_orders, then cancel_order_by_id, both Needs approval).

## Example: the NVDA ticket, Monday November 23, 2026

```
#1 READY  (PAPER account)
   Buy 6 NVDA at market, good till canceled
   with a stop-loss at 109.43 and a take-profit at 165.18 (they cancel each other)
   max loss at the stop: $96.60
   Claude will call place_stock_order with exactly:
   {"symbol": "NVDA", "side": "buy", "qty": "6", "type": "market", "time_in_force": "gtc", "order_class": "bracket", "take_profit_limit_price": "165.18", "stop_loss_stop_price": "109.43"}
```

"sure" is not recorded. "yes buy 6 TSLA" is not recorded (wrong stock). "yes,
buy 6 NVDA" is.

## Safety

- Education and tooling, not financial advice.
- Paper trading by default. Going live means the user changes `"paper": false` in their own
  config and uses live keys in their own Claude Desktop config. Never do either for them.
- Never place, change or cancel an order without the three gates above, and never batch yeses.
- No options, margin or short selling unless the config allows it and the user confirms.
