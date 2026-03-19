"""
On-chain data fetching — public data only.

Fetches treasury balances, token holdings, governance activity, and protocol
metrics from public on-chain sources. This data is NOT private — it's the
public input that gets analyzed privately via Venice.

Data sources:
  - Ethereum: Etherscan V2 API (free tier, requires API key)
  - Base: Blockscout API (free, no API key needed)
  - Governance: Snapshot GraphQL (free)
  - Protocol metrics: DeFi Llama (free)
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# Etherscan V2 API — free tier covers Ethereum mainnet
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

# Blockscout API — free, no key needed, covers Base
BLOCKSCOUT_BASE_URL = "https://base.blockscout.com/api/v2"

# Rate limits: Etherscan free tier ~5 calls/sec, Blockscout is generous
_ETHERSCAN_DELAY = 0.35  # ~2.8 calls/sec, safe for free tier


async def _fetch_etherscan(client: httpx.AsyncClient, params: dict) -> dict:
    """Call Etherscan V2 API for Ethereum mainnet. Returns result dict or {}."""
    await asyncio.sleep(_ETHERSCAN_DELAY)
    params["apikey"] = ETHERSCAN_API_KEY
    params["chainid"] = 1  # Ethereum mainnet
    try:
        resp = await client.get(ETHERSCAN_V2_URL, params=params)
        result = resp.json()
        logger.info("Etherscan action=%s status=%s", params.get("action"), result.get("status"))
        if result.get("status") == "1":
            return result
        logger.warning("Etherscan non-success: %s — %s", result.get("message", ""), result.get("result", ""))
    except Exception as e:
        logger.error("Etherscan failed: %s", e)
    return {}


async def _fetch_base_balance(client: httpx.AsyncClient, address: str) -> dict:
    """Fetch native ETH balance on Base via Blockscout."""
    try:
        resp = await client.get(f"{BLOCKSCOUT_BASE_URL}/addresses/{address}")
        if resp.status_code == 200:
            data = resp.json()
            # Blockscout returns coin_balance in wei as a string
            wei = int(data.get("coin_balance", "0") or "0")
            balance = wei / 1e18
            return {"balance": balance, "tx_count": data.get("transactions_count", 0)}
        logger.warning("Blockscout address lookup returned %d", resp.status_code)
    except Exception as e:
        logger.error("Blockscout address fetch failed: %s", e)
    return {}


async def _fetch_base_tokens(client: httpx.AsyncClient, address: str) -> list:
    """Fetch ERC-20 token balances on Base via Blockscout."""
    try:
        resp = await client.get(f"{BLOCKSCOUT_BASE_URL}/addresses/{address}/token-balances")
        if resp.status_code == 200:
            return resp.json()
        logger.warning("Blockscout token-balances returned %d", resp.status_code)
    except Exception as e:
        logger.error("Blockscout token fetch failed: %s", e)
    return []


async def _fetch_base_txs(client: httpx.AsyncClient, address: str, limit: int = 10) -> list:
    """Fetch recent transactions on Base via Blockscout."""
    try:
        resp = await client.get(
            f"{BLOCKSCOUT_BASE_URL}/addresses/{address}/transactions",
            params={"limit": limit},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", [])
        logger.warning("Blockscout transactions returned %d", resp.status_code)
    except Exception as e:
        logger.error("Blockscout tx fetch failed: %s", e)
    return []


async def fetch_treasury_data(address: str) -> dict:
    """
    Fetch public treasury data for an address across Ethereum and Base.

    - Ethereum data via Etherscan V2 API (free tier, requires ETHERSCAN_API_KEY)
    - Base data via Blockscout API (free, no key needed)

    Returns native balance, token balances, and recent transaction activity.
    All data is publicly available on-chain.
    """
    data = {
        "address": address,
        "chains": {},
        "token_balances": {},
        "total_tx_count": 0,
        "data_source": "public on-chain data (Ethereum via Etherscan, Base via Blockscout)",
    }

    async with httpx.AsyncClient(timeout=15) as client:

        # ── Ethereum (Etherscan V2) ──────────────────────────
        if ETHERSCAN_API_KEY:
            logger.info("Fetching Ethereum data for %s via Etherscan V2", address)

            # Native balance
            result = await _fetch_etherscan(client, {
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
            })
            if result:
                wei = int(result["result"])
                balance = wei / 1e18
                data["chains"]["ethereum"] = {
                    "native_balance": f"{balance:.6f} ETH",
                    "balance_raw": balance,
                }

            # ERC-20 token transfers
            result = await _fetch_etherscan(client, {
                "module": "account",
                "action": "tokentx",
                "address": address,
                "page": "1",
                "offset": "100",
                "sort": "desc",
            })
            if result:
                for tx in result.get("result", [])[:50]:
                    symbol = tx.get("tokenSymbol", "UNKNOWN")
                    if symbol not in data["token_balances"]:
                        data["token_balances"][symbol] = {
                            "contract": tx.get("contractAddress", ""),
                            "chain": "ethereum",
                            "recent_activity": True,
                        }

            # Recent transactions
            result = await _fetch_etherscan(client, {
                "module": "account",
                "action": "txlist",
                "address": address,
                "page": "1",
                "offset": "10",
                "sort": "desc",
            })
            if result:
                tx_count = len(result.get("result", []))
                data["total_tx_count"] += tx_count
                if "ethereum" in data["chains"]:
                    data["chains"]["ethereum"]["recent_tx_count"] = tx_count
        else:
            logger.warning("ETHERSCAN_API_KEY not set — skipping Ethereum data")

        # ── Base (Blockscout — free, no key) ─────────────────
        logger.info("Fetching Base data for %s via Blockscout", address)

        base_info = await _fetch_base_balance(client, address)
        if base_info:
            balance = base_info["balance"]
            tx_count = base_info.get("tx_count", 0)
            data["chains"]["base"] = {
                "native_balance": f"{balance:.6f} ETH (Base)",
                "balance_raw": balance,
                "recent_tx_count": tx_count,
            }
            data["total_tx_count"] += tx_count

        # Base token balances
        base_tokens = await _fetch_base_tokens(client, address)
        for item in base_tokens:
            token = item.get("token", {})
            symbol = token.get("symbol") or "UNKNOWN"
            if symbol not in data["token_balances"]:
                data["token_balances"][symbol] = {
                    "contract": token.get("address", ""),
                    "chain": "base",
                    "recent_activity": True,
                }

    if not data["chains"]:
        if not ETHERSCAN_API_KEY:
            data["error"] = "Etherscan API key not set (Base data may still be available)"
        else:
            data["error"] = "No on-chain data found for this address"

    return data


async def fetch_governance_data(target: str) -> dict:
    """
    Fetch public governance data for a protocol or DAO.

    Uses public APIs to gather proposal and voting information.
    """
    data = {
        "target": target,
        "data_source": "public on-chain/off-chain governance data",
        "proposals": [],
        "note": "Governance data aggregated from public sources",
    }

    # Try Snapshot (off-chain governance)
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            query = """
            query Proposals($space: String!) {
                proposals(
                    first: 10,
                    skip: 0,
                    where: { space_in: [$space] },
                    orderBy: "created",
                    orderDirection: desc
                ) {
                    id
                    title
                    state
                    scores_total
                    votes
                    created
                    end
                }
            }
            """
            resp = await client.post(
                "https://hub.snapshot.org/graphql",
                json={"query": query, "variables": {"space": target}},
            )
            result = resp.json()
            proposals = result.get("data", {}).get("proposals", [])
            for p in proposals[:10]:
                data["proposals"].append(
                    {
                        "title": p.get("title", ""),
                        "state": p.get("state", ""),
                        "votes": p.get("votes", 0),
                        "scores_total": p.get("scores_total", 0),
                    }
                )
        except Exception:
            data["note"] = (
                "Could not fetch Snapshot data — "
                "target may use on-chain governance only"
            )

    return data


async def fetch_risk_data(target: str) -> dict:
    """
    Fetch public risk-relevant data for a protocol.

    Aggregates TVL, audit status, and dependency information from
    public sources.
    """
    data = {
        "target": target,
        "data_source": "public protocol data",
        "tvl": None,
        "protocols": [],
    }

    # Try DeFi Llama for TVL data
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"https://api.llama.fi/protocol/{target.lower()}"
            )
            if resp.status_code == 200:
                result = resp.json()
                data["tvl"] = result.get("currentChainTvls", {})
                data["name"] = result.get("name", target)
                data["category"] = result.get("category", "Unknown")
                data["chains"] = result.get("chains", [])
                audits = result.get("audits", "0")
                data["audit_count"] = audits
                data["audit_links"] = result.get("audit_links", [])
        except Exception:
            data["note"] = "Could not fetch DeFi Llama data"

    return data


async def fetch_due_diligence_data(target: str) -> dict:
    """
    Fetch public data for due diligence on an address or protocol.
    """
    data = {
        "target": target,
        "data_source": "public on-chain data",
    }

    # If it looks like an address, fetch account data
    if target.startswith("0x") and len(target) == 42:
        data.update(await fetch_treasury_data(target))
    else:
        data.update(await fetch_risk_data(target))

    return data


DATA_FETCHERS = {
    "treasury": fetch_treasury_data,
    "governance": fetch_governance_data,
    "risk": fetch_risk_data,
    "due_diligence": fetch_due_diligence_data,
}


async def fetch_data_for_analysis(analysis_type: str, target: str) -> dict:
    """Route to the appropriate data fetcher."""
    fetcher = DATA_FETCHERS.get(analysis_type, fetch_due_diligence_data)
    return await fetcher(target)


def summarize_data_used(analysis_type: str, chain_data: dict) -> list[str]:
    """Produce a human-readable summary of what data sources were consulted."""
    lines: list[str] = []

    if analysis_type == "treasury":
        chains = chain_data.get("chains", {})
        for chain_name, info in chains.items():
            bal = info.get("native_balance", "0")
            txs = info.get("recent_tx_count", 0)
            source = "Etherscan" if chain_name == "ethereum" else "Blockscout"
            lines.append(f"{chain_name.title()}: {bal}, {txs} recent txs (via {source})")
        tokens = chain_data.get("token_balances", {})
        if tokens:
            names = ", ".join(sorted(k for k in tokens.keys() if k)[:8])
            extra = f" +{len(tokens) - 8} more" if len(tokens) > 8 else ""
            lines.append(f"Token activity: {names}{extra} ({len(tokens)} tokens seen)")
        if chain_data.get("error"):
            lines.append(chain_data["error"])
        if not lines:
            lines.append("No on-chain data available")

    elif analysis_type == "governance":
        proposals = chain_data.get("proposals", [])
        if proposals:
            active = sum(1 for p in proposals if p.get("state") == "active")
            closed = sum(1 for p in proposals if p.get("state") == "closed")
            lines.append(f"Snapshot proposals: {len(proposals)} fetched ({active} active, {closed} closed)")
        else:
            note = chain_data.get("note", "")
            lines.append(note or "No governance data found on Snapshot")

    elif analysis_type == "risk":
        tvl = chain_data.get("tvl")
        if tvl:
            total = sum(v for v in tvl.values() if isinstance(v, (int, float)))
            chains = chain_data.get("chains", [])
            lines.append(f"TVL: ${total:,.0f} across {len(chains)} chains (via DeFi Llama)")
        category = chain_data.get("category")
        if category:
            lines.append(f"Category: {category}")
        audits = chain_data.get("audit_count", "0")
        lines.append(f"Audits on record: {audits}")
        if not tvl:
            lines.append(chain_data.get("note", "No DeFi Llama data found"))

    elif analysis_type == "due_diligence":
        # Due diligence reuses treasury or risk fetchers
        if chain_data.get("chains"):
            lines.extend(summarize_data_used("treasury", chain_data))
        elif chain_data.get("tvl"):
            lines.extend(summarize_data_used("risk", chain_data))
        else:
            lines.append("Limited public data available for this target")

    return lines or ["No on-chain data sources consulted"]
