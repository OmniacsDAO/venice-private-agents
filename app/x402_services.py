"""
x402 service integrations — public actions with on-chain receipts.

These functions call x402-powered services to produce
trustworthy public outputs from Venice's private analysis:

- x402-pastebin:    Report storage (plain text)
- x402-timecapsule: Time-locked disclosures

Every call is an x402 USDC micropayment on Base — creating an
immutable, auditable trail of the agent's actions without revealing
the private content that was analyzed.
"""

import asyncio
import json
import os
from typing import Optional

PASTEBIN_URL = os.getenv("X402_PASTEBIN_URL", "https://pastebin.0000402.xyz")
TIMECAPSULE_URL = os.getenv(
    "X402_TIMECAPSULE_URL", "https://timecapsule.0000402.xyz"
)

# x402 payment client — handles the 402 → sign → retry flow automatically
_x402_client = None


def get_x402_client():
    """
    Get or create an x402-enabled requests session.

    The x402 client automatically handles the payment flow:
    1. Send request → receive 402 Payment Required
    2. Parse payment requirements from X-Payment-Required header
    3. Sign USDC payment authorization
    4. Retry with X-Payment header

    Uses eth_account with a private key for signing, matching the
    pattern used across all x402 Collections services.
    """
    global _x402_client
    if _x402_client is not None:
        return _x402_client

    from eth_account import Account

    from x402 import x402ClientSync
    from x402.http.clients.requests import x402_requests
    from x402.mechanisms.evm.exact import ExactEvmScheme
    from x402.mechanisms.evm.signers import EthAccountSigner

    private_key = os.getenv("AGENT_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError(
            "AGENT_PRIVATE_KEY must be set for x402 payments"
        )

    account = Account.from_key(private_key)
    signer = EthAccountSigner(account)
    client = x402ClientSync()
    # Register for Base Mainnet (eip155:8453)
    network = "eip155:8453" if os.getenv("NETWORK") == "base" else "eip155:84532"
    client.register(network, ExactEvmScheme(signer))
    _x402_client = x402_requests(client)
    return _x402_client


async def store_report(report: dict) -> dict:
    """
    Store the full analysis report via x402-pastebin (plain text).

    Cost: ~$0.01 USDC on Base.
    """
    report_text = json.dumps(report, indent=2)

    try:
        client = get_x402_client()
        response = await asyncio.to_thread(
            client.post,
            f"{PASTEBIN_URL}/paste",
            json={
                "content": report_text,
                "language": "json",
            },
        )
        result = response.json()
        return {
            "pastebin_token": result.get("token"),
            "retrieval_url": f"{PASTEBIN_URL}/paste/{result.get('token')}",
            "cost_usdc": 0.01,
        }
    except Exception as e:
        return {
            "pastebin_token": None,
            "retrieval_url": None,
            "cost_usdc": 0.0,
            "error": str(e),
        }


async def seal_report(report: dict, unlock_at: str, label: str) -> dict:
    """
    Seal the full report in a time capsule via x402-timecapsule.

    Content is inaccessible until the unlock time, then free to open.
    Useful for delayed disclosure of sensitive analyses.
    Cost: $0.05 USDC on Base.
    """
    report_text = json.dumps(report, indent=2)

    try:
        client = get_x402_client()
        response = await asyncio.to_thread(
            client.post,
            f"{TIMECAPSULE_URL}/seal",
            json={
                "content": report_text,
                "unlock_at": unlock_at,
                "label": label,
            },
        )
        result = response.json()
        return {
            "capsule_token": result.get("token"),
            "unlock_at": result.get("unlock_at"),
            "status_url": f"{TIMECAPSULE_URL}/status/{result.get('token')}",
            "cost_usdc": 0.05,
        }
    except Exception as e:
        return {
            "capsule_token": None,
            "cost_usdc": 0.0,
            "error": str(e),
        }


def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[: max_len - 3] + "..."
