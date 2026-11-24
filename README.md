==============

A drawdown guard for MyFundedPerps sandbox accounts. Watches a challenge
account's risk snapshot and closes all positions when the day's unrealized
loss hits a threshold you set. Built for the MyFundedPerps Builders Program.

## What it does

- Reads `GET /v1/accounts/{id}` for the live risk snapshot (equity, unrealized
  P&L, daily loss room, daily loss floor).
- Reads `GET /v1/positions?account_id=` for open positions.
- When daily loss ≥ `--max-loss-pct` (default 2% of starting balance),
  submits `POST /v1/accounts/{id}/close-all-positions` with an idempotency key.
- `--dry-run` evaluates without submitting closes.
- `--watch SECONDS` re-checks on a loop.

## Prerequisites

- Python 3.8+ (stdlib only — no external dependencies)
- A MyFundedPerps sandbox API key starting with `fp_test_` (create one at
  https://myfundedperpetuals.com/settings?section=api-keys under Test
  environment)

## Install & run

```bash
git clone https://github.com/<your-user>/drawdown-guard.git
cd drawdown-guard
export FP_API_KEY=fp_test_...your-sandbox-key...
python drawdown_guard.py \
  --account-id <your-sandbox-account-id> \
  --max-loss-pct 2
```

Omit `--account-id` to guard the first sandbox account returned by your key.

Dry-run (no trades):
```bash
python drawdown_guard.py --dry-run
```

Watch every 30s:
```bash
python drawdown_guard.py --watch 30
```

## Exit codes

- `0` — checked, no action needed
- `2` — positions closed because threshold was breached
- `1` — error

## Safety

- Sandbox only. This key will not work on the live host, and the guard never
  touches live accounts.
- Never commit `FP_API_KEY` to git. Add it to your shell env or a local
  `.env` you keep out of version control.
- Every close uses a fresh idempotency key so retries can't duplicate exposure.

## Built on

MyFundedPerps REST API v1 (sandbox host `sandbox.myfundedperpetuals.com`):
- `GET /v1/accounts` — list accounts
- `GET /v1/accounts/{id}` — account + risk snapshot
- `GET /v1/positions?account_id=` — open positions
- `POST /v1/accounts/{id}/close-all-positions` — close all

Docs: https://docs.myfundedperpetuals.com/quickstart
# drawdown-guard
