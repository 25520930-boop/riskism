#!/usr/bin/env python3
"""
Quick endpoint verifier for Riskism market APIs.

Calls each market endpoint and prints the JSON response so we can confirm
the vnstock3/vnstock-backed response format stays stable for the frontend.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Tuple


def fetch_json(url: str) -> Tuple[int, Dict[str, Any]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        status = response.getcode()
        body = response.read().decode("utf-8")
        return status, json.loads(body)


def print_section(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def check_keys(payload: Dict[str, Any], expected_keys: Iterable[str]) -> Tuple[bool, list[str]]:
    missing = [key for key in expected_keys if key not in payload]
    return len(missing) == 0, missing


def print_payload(label: str, url: str, payload: Dict[str, Any], expected_keys: Iterable[str] | None = None):
    print(f"[{label}] {url}")
    if expected_keys is not None:
        ok, missing = check_keys(payload, expected_keys)
        print(f"Format check: {'OK' if ok else 'MISSING KEYS'}")
        if missing:
            print(f"Missing: {missing}")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Riskism market endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument("--symbol", default="VCB", help="Vietnamese stock symbol to test")
    parser.add_argument("--days", type=int, default=5, help="History window")
    parser.add_argument("--search", default="VC", help="Symbol search query")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    symbol = args.symbol.upper()
    days = max(args.days, 2)
    search = args.search

    endpoints = [
        (
            f"GET /api/market/{symbol}?days={days}",
            f"{base_url}/api/market/{urllib.parse.quote(symbol)}?days={days}",
            ("symbol", "dates", "open", "high", "low", "close", "volume"),
        ),
        (
            f"GET /api/market/{symbol}/price",
            f"{base_url}/api/market/{urllib.parse.quote(symbol)}/price",
            ("symbol", "price", "timestamp"),
        ),
        (
            f"GET /api/market/{symbol}/risk",
            f"{base_url}/api/market/{urllib.parse.quote(symbol)}/risk",
            None,
        ),
        (
            f"GET /api/market/symbols/search?q={search}",
            f"{base_url}/api/market/symbols/search?q={urllib.parse.quote(search)}&limit=5",
            ("items", "query", "total"),
        ),
        (
            f"GET /api/market/VNINDEX?days={days}",
            f"{base_url}/api/market/VNINDEX?days={days}",
            ("symbol", "dates", "open", "high", "low", "close", "volume"),
        ),
        (
            "GET /api/market/VNINDEX/price",
            f"{base_url}/api/market/VNINDEX/price",
            ("symbol", "price", "timestamp"),
        ),
    ]

    print_section("RISKISM MARKET API FORMAT CHECK")
    failures = 0

    for label, url, expected_keys in endpoints:
        try:
            status, payload = fetch_json(url)
            print(f"HTTP {status}")
            print_payload(label, url, payload, expected_keys=expected_keys)
        except urllib.error.HTTPError as exc:
            failures += 1
            print(f"[{label}] HTTP ERROR {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        except urllib.error.URLError as exc:
            failures += 1
            print(f"[{label}] URL ERROR: {exc}")
        except Exception as exc:
            failures += 1
            print(f"[{label}] ERROR: {exc}")

    print_section("SUMMARY")
    if failures:
        print(f"{failures} endpoint(s) failed.")
        return 1

    print("All endpoint calls completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
