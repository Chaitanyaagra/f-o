# AI TradePro V9 — Review & Changes

## What this project actually is

- `index.html` — a self-contained **paper-trading simulator**. Prices come from a
  random-walk generator (`MarketEngine`) running in the browser. The "AI Signal"
  is a fixed rule score from EMA-vs-SMA, RSI, and the last candle's direction.
- `backend.py` — a **separate** FastAPI service that logs into Angel One (SmartAPI)
  and can place **real** F&O orders.

**The two are not connected.** Nothing in the page ever calls the backend, so today
every "trade" is simulated. That's fine as a demo, but the naming ("AI", "Auto-Quant",
"V9 Final") oversells it, and the pieces become risky the moment they're wired together.

I did **not** wire live auto-trading. Auto-trade stays simulation-only by design; if
you ever connect real execution it should be manual and confirmation-gated.

---

## Bugs fixed

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | index.html | `index-selector` was referenced in JS but no such element existed, so **BANKNIFTY was dead** and you couldn't switch instruments. | Added the selector in the header. |
| 2 | index.html | RSI loop reads `data[i-1]`; when the series length equals the period it touches `data[-1]` → `NaN`. | Guard changed to `length <= period`. |
| 3 | index.html | Failed entries (`val > bal`) were swallowed with `console.log("Margin Low")` — no user feedback. | Added a visible toast with the exact shortfall. |
| 4 | index.html | `this.m.tick()` returns `undefined` before data exists; used in comparisons. | Coerced with `|| 0`. |
| 5 | index.html | The "Daily Limit −₹5,000" header was **decorative** — never enforced. | Now a real halt: blocks entries + disables auto-trade when net P/L ≤ −limit. |

## Safety guardrails added (frontend)

- **Daily-loss halt** — trading stops (manual and auto) once the limit is hit, and
  auto-trade can't be re-armed while halted.
- **Auto-trade cap** — `MAX_AUTO_TRADES` per session, then it switches itself off.
- **Honest labelling** — a "SIMULATION" badge replaces the always-on "MARKET OPEN",
  and a note under the signal panel explains that "confidence" is a rule score, not a
  probability or a prediction, running on simulated prices.

## Security fixes (backend) — these were the serious ones

| # | Issue | Fix |
|---|-------|-----|
| 1 | Broker **password + TOTP secret + API key were sent over HTTP** in the request body. The TOTP *secret* (the seed) is the crown jewel — with it, anyone can generate your 2FA forever. | Credentials now live only in server-side env vars (`.env`). The browser sends nothing sensitive. |
| 2 | `allow_origins=["*"]` **with** `allow_credentials=True` — invalid per spec, and it let any website you visit call your order engine. | Restricted to an explicit local origins list; credentials off. |
| 3 | `/api/place-order` had **no auth** — anyone reaching the server could trade. | Requires a session token (minted at login) via `X-Session-Token`. |
| 4 | No accidental-order protection. | Orders **default to DRY_RUN**; a live order needs `DRY_RUN=false` **and** `confirm=true`. |
| 5 | Exchange/product/variety hardcoded to `NFO`/`INTRADAY`/`NORMAL`. | Now request parameters. |
| 6 | Binds `0.0.0.0`, exposing the order engine to your whole LAN. | Defaults to `127.0.0.1`. |
| 7 | `data['status']` etc. accessed without type checks. | Defensive parsing + structured errors + order logging. |

---

## Honest caveats (please read)

- I can make the **code** solid; I can't tell you the strategy is profitable. The
  signal here is a basic momentum heuristic with no demonstrated edge, backtested or
  live. Treat it as a UI/plumbing demo, not a money-maker.
- Buying options with an auto-firing rule at fixed 30-s intervals, no slippage or
  liquidity modelling, and a toy confidence score is a fast way to lose real capital
  if pointed at a live account. Keep `DRY_RUN=true` until you've tested end-to-end,
  and never leave unattended automation trading real money.
- This is a personal/local tool. Don't expose the backend to the public internet.

## Recommended next steps (not auto-applied)

1. Decide: is this a **simulator** (delete `backend.py`) or a **live tool**
   (wire the page to the backend, manual + confirm only)?
2. Move brokerage/tax/slippage into a realistic cost model if you want the P/L to mean anything.
3. Add persistence (positions/history) and a proper backtest harness before trusting any signal.
4. Multi-user or hosted use would need per-user sessions, HTTPS, and rate limiting.

---

## Later additions (robustness + honesty)

- **Stable signals** — neutral band + 5-read confirmation (hysteresis) so the call
  doesn't flip every tick; shows honest WAIT when there's no confirmed trend.
- **Live chart mode** — pulls real Angel One candles (Connect Broker → Go Live);
  falls back to simulation on any error instead of freezing.
- **Real market hours** — sim freezes when NSE is closed (IST 9:15–15:30, Mon–Fri);
  a Practice toggle lets you run it after hours.
- **Expiry Guide + hold-time** — matches expiry/holding-window to your plan (education,
  not a profit call).
- **Backtest** — runs the same rule over history; reports win rate, profit factor,
  drawdown, and net AFTER an assumed cost/slippage per trade.
- **Robust fetch (backend)** — retry + exponential backoff + rate-limit cooldown +
  short TTL cache on LTP/candle calls (pattern adapted from HKUDS/AI-Trader, MIT).
- **Realistic F&O cost model** — brokerage + STT + exchange txn + SEBI + stamp + GST
  applied on exit, so paper P&L reflects what you'd actually net. Rates are approximate
  and configurable in CONSTANTS.CHARGES — verify against current regulations.

None of this makes the strategy profitable or predictive. It makes the tool honest,
reliable, and realistic. Test in paper/DRY_RUN before risking real money.

## More additions

- **Risk-based position sizing** — Auto Calc now shows exactly how much you're
  risking (₹ and %) and the max loss if SL hits, so lots are chosen by risk, not gut.
- **Persistent trade journal** — every closed paper trade is saved on your device and
  restored on reload; the analytics tab shows win rate, profit factor, and max drawdown.
- **CSV export / clear** — download your whole journal as CSV to review over weeks/months.

## Learn module

- **Learn Chart Patterns** — a beginner-friendly reference (Support/Resistance, Up/Down
  trend, Double Top/Bottom, Head & Shoulders, Ascending Triangle, Bull Flag, Candles &
  Doji) with small hand-drawn inline diagrams and plain-English notes. Clearly framed:
  patterns are tendencies, not guarantees.

## Auto pattern detection

- **Scan Pattern** (button on the chart) — analyses the current candles (live or sim),
  finds swing pivots, and identifies a likely pattern (Double Top/Bottom, Head &
  Shoulders, Ascending Triangle, Uptrend/Downtrend, or Range), showing the matching
  diagram and what it usually indicates. Clearly labelled as an approximate hint —
  automated pattern detection is fuzzy and often wrong; confirm before acting.

## Learning + discipline tools

- **Pattern Quiz** — shows a pattern diagram with 4 choices, keeps score, and explains
  what the pattern means after each answer. Reinforces the Learn module.
- **Pre-Trade Checklist** — before entering, auto-checks direction, stop-loss,
  reward:risk, risk ≤ 2% of capital, and market-open; plus honest manual confirmations
  (no expiry-hour theta, news checked, sized by risk, accepts a loss). Green light only
  when everything passes. Discipline improves odds — it does not guarantee profit.

## Live auto trend/pattern

- **Auto trend + pattern badge** on the chart — updates itself every few seconds
  (live or sim), showing the current trend (Up/Down/Sideways) and any detected pattern.
- **Chart markers** — the pivots forming the detected pattern are circled on the chart
  (peaks above, troughs below). Approximate and often wrong — a hint, not a signal.
