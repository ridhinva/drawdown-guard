#!/usr/bin/env python3
"""Drawdown Guard for MyFundedPerps sandbox.

A self-contained CLI that watches a challenge account's open positions and
risk snapshot, then closes all positions when the day's unrealized loss breaches
a threshold you set. Built for the MyFundedPerps Builders Program (sandbox only).
                                                                                  Usage:
    FP_API_KEY=fp_test_... python drawdown_guard.py \
        --account-id <id> --max-loss-pct 2
                                                                                  Exit codes:
    0   guard checked, no action needed (or close completed)
    1   error
    2   positions closed because loss threshold was breached
"""
                                                                                  from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from urllib import error, request

DEFAULT_BASE_URL = "https://sandbox.myfundedperpetuals.com"


class GuardError(Exception):
    pass


def _api_get(base_url: str, api_key: str, path: str, params: str = "") -> dict:
    url = f"{base_url}{path}{params}"
    req = request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as e:
        body = e.read().decode()
        raise GuardError(f"GET {path} -> HTTP {e.code}: {body}") from e


def _api_post(
    base_url: str, api_key: str, path: str, body: dict, idempotency_key: str
) -> dict:
    url = f"{base_url}{path}"
    data = json.dumps(body).encode()
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as e:
        body = e.read().decode()
        raise GuardError(f"POST {path} -> HTTP {e.code}: {body}") from e


def list_accounts(base_url: str, api_key: str) -> list[dict]:
    return _api_get(base_url, api_key, "/v1/accounts").get("data", [])


def risk_snapshot(base_url: str, api_key: str, account_id: str) -> dict:
    return _api_get(base_url, api_key, f"/v1/accounts/{account_id}").get("data", {})


def list_positions(base_url: str, api_key: str, account_id: str) -> list[dict]:
    return _api_get(
        base_url, api_key, "/v1/positions", f"?account_id={account_id}"
    ).get("data", [])


def close_all_positions(base_url: str, api_key: str, account_id: str) -> dict:
    key = f"dd-guard-{uuid.uuid4()}"
    return _api_post(
        base_url,
        api_key,
        f"/v1/accounts/{account_id}/close-all-positions",
        {},
        key,
    )


def guard_once(
    base_url: str,
    api_key: str,
    account_id: str,
    max_loss_pct: float,
    dry_run: bool = False,
) -> dict:
    """Run one guard check. Returns a result dict."""
    risk = risk_snapshot(base_url, api_key, account_id)
    r = risk.get("risk", {})
    positions = list_positions(base_url, api_key, account_id)

    equity = r.get("equity", 0)
    starting = risk.get("starting_balance", equity)
    unrealized = r.get("unrealized_pnl", 0)
    daily_loss_room = r.get("daily_loss_room", 0)

    # Loss as a percent of the starting balance for the day.
    loss_pct = (starting - equity) / starting * 100 if starting else 0
    breached = loss_pct >= max_loss_pct

    result = {
        "account_id": account_id,
        "account_name": risk.get("name"),
        "equity": equity,
        "starting_balance": starting,
        "unrealized_pnl": unrealized,
        "daily_loss_pct": round(loss_pct, 4),
        "max_loss_pct": max_loss_pct,
        "breached": breached,
        "open_positions": len(positions),
        "action": "none",
    }

    if not breached:
        return result

    if dry_run:
        result["action"] = "would_close"
        return result

    close_result = close_all_positions(base_url, api_key, account_id)
    result["action"] = "closed"
    result["close"] = close_result
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MyFundedPerps drawdown guard (sandbox).")
    p.add_argument("--account-id", help="Account to guard (defaults to first sandbox account)")
    p.add_argument(
        "--max-loss-pct",
        type=float,
        default=2.0,
        help="Close all positions when daily loss reaches this %% of starting balance (default 2)",
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("FP_BASE_URL", DEFAULT_BASE_URL),
        help="API host (default sandbox)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate but do not submit closes",
    )
    p.add_argument(
        "--watch",
        type=int,
        metavar="SECONDS",
        help="Re-run the guard every N seconds instead of once",
    )
    args = p.parse_args(argv)

    api_key = os.environ.get("FP_API_KEY")
    if not api_key:
        print("error: set FP_API_KEY (your fp_test_ sandbox key)", file=sys.stderr)
        return 1

    # Resolve account.
    account_id = args.account_id
    if not account_id:
        accounts = list_accounts(args.base_url, api_key)
        if not accounts:
            print("error: no sandbox accounts found for this key", file=sys.stderr)
            return 1
        account_id = accounts[0]["id"]
        print(f"no --account-id given; using {account_id} ({accounts[0]['name']})")

    def run_once() -> int:
        try:
            result = guard_once(
                args.base_url, api_key, account_id, args.max_loss_pct, args.dry_run
            )
        except GuardError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        print(
            f"[{result['account_name']}] equity={result['equity']:.2f} "
            f"daily_loss={result['daily_loss_pct']}% "
            f"threshold={result['max_loss_pct']}% "
            f"positions={result['open_positions']} "
            f"action={result['action']}"
        )
        if result.get("close"):
            print(json.dumps(result["close"], indent=2))
        return 2 if result["action"] == "closed" else 0

    if args.watch:
        while True:
            code = run_once()
            time.sleep(args.watch)
            if code == 2:
                # Closed positions; keep watching in case new ones open.
                continue
    else:
        return run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main())
