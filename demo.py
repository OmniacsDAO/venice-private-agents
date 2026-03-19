"""
Veiled Oracle Demo Script

Demonstrates the full private-analysis → public-verdict pipeline:
1. Sends a treasury analysis request for a well-known DAO address
2. Venice AI analyzes the data privately (no data retention)
3. Public verdict returned directly in the API response
4. Full report stored via x402-pastebin
5. Shows the itemized x402 spending receipts

The /analyze endpoint is protected by the x402 payment gate — it returns
402 Payment Required. This demo auto-signs a USDC payment and retries
with the X-Payment header. Requires AGENT_PRIVATE_KEY in the environment.

Requirements:
  - The Veiled Oracle service must be running (uvicorn app.main:app)
  - .env must be configured with Venice, CDP, and x402 credentials
  - AGENT_PRIVATE_KEY must be set for the demo to sign payments

Usage:
  python demo.py
  python demo.py --target 0x0BC3807Ec262cB779b38D65b38FA7364e79901c4
  python demo.py --type governance --target uniswap
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
import requests

load_dotenv()

BASE_URL = "http://localhost:8000"


NETWORKS = {
    "base": "eip155:8453",
    "base-sepolia": "eip155:84532",
}


def _create_x402_session():
    """Create an x402-enabled requests session for paying the payment gate."""
    try:
        from eth_account import Account
        from x402 import x402ClientSync
        from x402.http.clients.requests import x402_requests
        from x402.mechanisms.evm.exact import ExactEvmScheme
        from x402.mechanisms.evm.signers import EthAccountSigner
    except ImportError:
        print("  ERROR: x402 SDK not installed.")
        print("  Install with: pip install 'x402[evm,httpx]' eth-account")
        sys.exit(1)

    private_key = os.environ.get("AGENT_PRIVATE_KEY", "")
    if not private_key:
        print("  ERROR: x402 payment gate is active — /analyze returned 402.")
        print("  Set AGENT_PRIVATE_KEY in your environment to auto-sign payments.")
        sys.exit(1)

    network = os.environ.get("NETWORK", "base")
    caip2 = NETWORKS.get(network, NETWORKS["base"])

    account = Account.from_key(private_key)
    signer = EthAccountSigner(account)

    client = x402ClientSync()
    client.register(caip2, ExactEvmScheme(signer))

    return x402_requests(client)


def run_analysis(analysis_type: str, target: str):
    """Run a full analysis and display results."""

    print(f"\n{'='*70}")
    print(f"  Veiled Oracle — {analysis_type.upper()} Analysis")
    print(f"  Target: {target}")
    print(f"{'='*70}\n")

    # Step 1: Health check
    print("[1/3] Checking service health...")
    resp = requests.get(f"{BASE_URL}/health")
    if resp.status_code != 200:
        print(f"  ERROR: Service not healthy (HTTP {resp.status_code})")
        sys.exit(1)
    health = resp.json()
    print(f"  Venice model: {health['venice_model']}")
    print(f"  Network: {health['network']}")
    print(f"  Budget remaining: ${health['total_budget_remaining']:.2f}")

    # Step 2: Run analysis (x402 session auto-handles 402 → sign → retry)
    print(f"\n[2/3] Running private analysis via Venice AI...")
    print(f"  (data sent to Venice with no-data-retention — zero trace)")
    print(f"  (x402 payment will be signed automatically)")
    session = _create_x402_session()
    analyze_url = f"{BASE_URL}/analyze"
    payload = {
        "analysis_type": analysis_type,
        "target": target,
        "context": "Provide a thorough analysis with specific findings.",
        "publish_verdict": True,
    }
    resp = session.post(analyze_url, json=payload)

    if resp.status_code != 200:
        print(f"  ERROR: Analysis failed (HTTP {resp.status_code})")
        print(f"  {resp.text}")
        sys.exit(1)

    # Show x402 payment receipt if present
    if "X-Payment-Response" in resp.headers:
        try:
            from x402.http import decode_payment_response_header
            receipt = decode_payment_response_header(resp.headers["X-Payment-Response"])
            print(f"  ✓ x402 payment settled: {json.dumps(receipt, indent=4)}")
        except Exception:
            print(f"  ✓ x402 payment settled (receipt in X-Payment-Response header)")

    result = resp.json()

    # Step 3: Display results
    print(f"\n[3/3] Results\n")

    # Verdict (public)
    verdict = result["verdict"]
    severity_colors = {
        "healthy": "\033[92m",  # green
        "caution": "\033[93m",  # yellow
        "warning": "\033[91m",  # red
        "critical": "\033[91m\033[1m",  # bold red
    }
    reset = "\033[0m"
    color = severity_colors.get(verdict["severity"], "")

    print(f"  PUBLIC VERDICT")
    print(f"  Severity: {color}{verdict['severity'].upper()}{reset}")
    print(f"  Summary:  {verdict['summary']}")

    # Data sources used
    data_used = result.get("data_used", [])
    if data_used:
        print(f"\n  DATA SOURCES")
        for line in data_used:
            print(f"  - {line}")

    # Report reference
    rpt = result.get("report")
    if rpt and rpt.get("retrieval_url"):
        print(f"\n  FULL REPORT")
        print(f"  View: {rpt['retrieval_url']}")

    # Time capsule
    capsule = result.get("time_capsule")
    if capsule and capsule.get("capsule_token"):
        print(f"\n  TIME CAPSULE")
        print(f"  Unlock at: {capsule['unlock_at']}")
        print(f"  Status:    {capsule['status_url']}")

    # Spending
    print(f"\n  x402 SPENDING RECEIPTS")
    for s in result.get("spending", []):
        print(f"  ${s['amount_usdc']:.2f}  {s['service']:20s}  {s['description']}")
    print(f"  {'─'*50}")
    print(f"  ${result['total_spent_usdc']:.2f}  TOTAL")

    # Privacy guarantee
    print(f"\n  PRIVACY")
    print(f"  {result['privacy_guarantee']}")

    print(f"\n{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Veiled Oracle Demo")
    parser.add_argument(
        "--type",
        choices=["treasury", "governance", "risk", "due_diligence"],
        default="treasury",
        help="Analysis type (default: treasury)",
    )
    parser.add_argument(
        "--target",
        default="0x0BC3807Ec262cB779b38D65b38FA7364e79901c4",
        help="Target address or protocol name",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Veiled Oracle base URL",
    )
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    run_analysis(args.type, args.target)


if __name__ == "__main__":
    main()
