# Veiled Oracle

**Private Intelligence, Public Verdicts.**

An agent that uses Venice AI's no-data-retention inference to analyze sensitive on-chain data privately, then produces trustworthy public outputs via x402-powered services on Base.

```
Private cognition (Venice)  →  Public action (x402 on Base)
─────────────────────────      ─────────────────────────────
Sensitive data analysis        Public verdicts (API response)
No-data-retention inference    Full reports on x402-pastebin
Zero prompt logging            On-chain payment receipts
Confidential reasoning         Time-locked disclosures
```

**Track:** Venice — Private Agents, Trusted Actions
**Hackathon:** Synthesis 2026
**Team:** Omniacs DAO

---

## Track Alignment

### Private Agents, Trusted Actions (Venice)

| Track Requirement | How Veiled Oracle Delivers |
|---|---|
| **Venice is load-bearing** | Venice is the core privacy guarantee — without it, sensitive financial data (treasury positions, governance strategies, risk assessments) would be stored by the inference provider. Replacing Venice with any other provider breaks the entire privacy promise. |
| **Private cognition → public action** | Raw data enters Venice (private, no retention) → split output produces a public verdict (severity + one sentence, zero sensitive details) and a full report stored on x402-pastebin. The agent thinks privately and acts publicly. |
| **Agents that keep secrets** | Two layers: (1) Venice no-data-retention inference, (2) time-locked disclosures via x402-timecapsule. The agent controls what is revealed and when. |
| **Agents that pay** | The agent both charges and spends via x402: callers pay $0.10 USDC to use `/analyze`, and the agent pays downstream services (pastebin, timecapsule) from its earnings. Self-sustaining value loop with on-chain receipts. |
| **Agents that trust** | Verdicts are returned directly in the API response along with `data_used` showing exactly which data sources were consulted. Reports and time-locked disclosures provide verifiable, auditable public records. |
| **On-chain artifacts** | x402 USDC payment transactions on Base, storage receipts — all on-chain or content-addressable. |
| **Ship something that works** | Full working FastAPI service with `/analyze` endpoint, CLI demo, Docker deployment. Four analysis types (treasury, governance, risk, due diligence) against real on-chain data sources. |

---

## The Problem

AI agents analyzing treasury positions, governance patterns, or protocol risks handle sensitive financial data — fund allocations, voting strategies, risk exposures, due diligence findings. Today, this data flows through inference providers who may store, log, or train on it. The analysis itself becomes an information leak.

DAOs need private intelligence with public accountability: the ability to analyze sensitive data confidentially while producing verifiable, trustworthy outputs that the broader community can rely on.

## The Solution

Veiled Oracle sits at the boundary between **private intelligence** and **public consequence** — exactly the layer the Venice track describes.

### Architecture

```
                     x402 payment ($0.10 USDC)
  ┌──────────┐    ─────────────────────────────▶  ┌──────────────────┐
  │  Caller  │                                    │   Veiled Oracle  │
  │  (agent  │  ◀─────────────────────────────    │   (this API)     │
  │  or user)│    verdict + report + data_used    └────────┬─────────┘
  └──────────┘                                             │
                                                           │ x402 payments
                                                           │ (agent pays)
                                                           ▼
                                              ┌──────────────────────┐
              ┌──────────────────┐            │   x402 Services      │
              │    Venice AI      │            │                      │
              │  No-data-         │◀───────────│  Pastebin → report   │
              │  retention        │            │  Capsule → sealed    │
              │  inference        │            │  Payments → receipts │
              └──────────────────┘            └──────────────────────┘
```

The caller pays `$0.10 USDC` via x402 to use `/analyze`. This payment covers the agent's downstream costs (Venice inference, x402-pastebin storage, x402-timecapsule sealing). The agent earns from callers and spends on downstream services — a self-sustaining x402 value loop.

The x402 payment gate is mandatory — the app refuses to start without CDP keys configured.

### Privacy Flow

1. **Public data in** — Agent fetches publicly available on-chain data from Ethereum (via Etherscan V2) and Base (via Blockscout) — treasury balances, token activity, governance proposals, TVL metrics. Optionally, the caller provides additional private context.

2. **Private analysis** — All data is sent to Venice AI for inference. Venice operates with **no data retention**: prompts and completions are processed in real-time and never stored, logged, or used for training. The raw data and all reasoning exist only in transit.

3. **Split output** — Venice returns two components:
   - **Public verdict**: A severity level (`healthy`/`caution`/`warning`/`critical`) and a one-sentence summary containing zero sensitive details — only the conclusion.
   - **Private report**: Detailed findings, risk factors, and recommendations — stored on x402-pastebin for retrieval.

4. **Public action** — The verdict is returned directly in the API response. The agent stores outputs via x402-powered services on Base:
   - **API response**: Verdict (severity + one-sentence summary) returned directly to the caller.
   - **x402-pastebin** ($0.01 USDC): Full report stored as plain text, retrievable by token.
   - **x402-timecapsule** ($0.05 USDC, optional): Full report sealed until a future date for delayed disclosure.

5. **Audit trail** — Every x402 service call is a USDC micropayment on Base. The on-chain record proves the agent acted (it spent money) without revealing what it analyzed.

### Why Venice is Load-Bearing

Venice is not a decorative integration — it is the core privacy guarantee:

- **Without Venice**: The agent's analysis prompts (containing sensitive financial data) would be stored by the inference provider, creating an information leak. The privacy promise would be hollow.
- **With Venice**: No-data-retention inference means sensitive treasury positions, governance strategies, and risk assessments pass through the system and leave zero trace. The agent can make authoritative public statements ("this treasury is healthy") without anyone being able to reconstruct the private data that led to that conclusion.

This is the "private cognition → trustworthy public action" pipeline the track describes.

## Analysis Types

| Type | What It Analyzes | Public Verdict Reveals | Private Report Contains |
|------|-----------------|----------------------|------------------------|
| **Treasury** | Wallet holdings on Ethereum + Base, token activity, tx history | Health status (healthy/caution/warning/critical) | Detailed positions, concentration risks, recommendations |
| **Governance** | DAO proposals, voting patterns, delegate behavior | Participation health level | Centralization risks, power concentration, voting anomalies |
| **Risk** | Protocol TVL, audits, dependency chains, liquidity | Risk severity | Exposure analysis, risk matrix, specific mitigations |
| **Due Diligence** | Project/address legitimacy, red flags | Trust level | Red flags found, legitimacy signals, detailed assessment |

## Spending Controls

Two layers of protection:

### 1. x402 Payment Gate (caller pays)

The `/analyze` endpoint is protected by x402 payment middleware. Callers must pay `$0.10 USDC` on Base before the request is processed. This means:

- **No free calls** — every analysis requires a signed USDC payment
- **Self-sustaining** — the agent earns from callers and spends on downstream services
- **No wallet drain risk** — the operator's wallet is funded by incoming payments, not drained by them

```bash
ANALYZE_PRICE_USDC=0.10   # Price callers pay per analysis (configurable)
```

### 2. Internal Budget Limits (agent spending cap)

The human operator also sets boundaries on the agent's downstream spending:

```bash
MAX_SPEND_PER_ANALYSIS=0.50   # Cap per single analysis
MAX_TOTAL_SPEND=10.00          # Lifetime cap before human re-approval
```

The agent self-enforces these limits. When the budget is exhausted, it returns HTTP 402 and requires the human to increase the limit.

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/omniacsdao/veiled-oracle.git
cd veiled-oracle
cp .env.example .env
# Edit .env with your keys
```

### 2. Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3. Run with Docker

```bash
docker build -t veiled-oracle .
docker run -d -p 8000:8000 --env-file .env veiled-oracle
```

### 4. Use the API

```bash
# Health check (free, no payment required)
curl http://localhost:8000/health

# Run a treasury analysis (x402-gated — returns 402 first)
# Step 1: First call returns 402 Payment Required with payment details
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_type": "treasury",
    "target": "0x0BC3807Ec262cB779b38D65b38FA7364e79901c4",
    "context": "This is the Gitcoin treasury. We want to know if allocations look healthy.",
    "publish_verdict": true
  }'
# Response: HTTP 402 with x402 payment instructions
# { "accepts": [{ "scheme": "exact", "price": "$0.10", "network": "eip155:8453", ... }] }

# Step 2: Sign a USDC payment and retry with X-Payment header
# (x402-compatible agents/clients handle this automatically)

# Run a governance analysis
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_type": "governance",
    "target": "uniswap",
    "publish_verdict": true
  }'

# Run a risk analysis with time-locked disclosure
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_type": "risk",
    "target": "aave",
    "publish_verdict": true,
    "seal_until": "2026-04-01T00:00:00Z"
  }'
```

### 5. Retrieve full report

```bash
# Use the pastebin_token from the analysis response
curl https://pastebin.0000402.xyz/paste/{token}
```

## Response Example

```json
{
  "analysis_id": "a1b2c3d4-...",
  "analysis_type": "treasury",
  "target": "0x0BC3807Ec262cB779b38D65b38FA7364e79901c4",
  "timestamp": "2026-03-16T14:30:00+00:00",
  "privacy_guarantee": "All raw data processed via Venice AI (no-data-retention inference). Sensitive inputs are never stored, logged, or persisted by any component in the pipeline.",
  "verdict": {
    "severity": "healthy",
    "summary": "Treasury shows diversified holdings with adequate runway and no critical concentration risks."
  },
  "data_used": [
    "Ethereum: 0.001234 ETH, 3 recent txs (via Etherscan)",
    "Base: 1.500000 ETH (Base), 10 recent txs (via Blockscout)",
    "Token activity: DAI, USDC, WETH (3 tokens seen)"
  ],
  "report": {
    "pastebin_token": "c4d5e6f7-...",
    "retrieval_url": "https://pastebin.0000402.xyz/paste/c4d5e6f7-..."
  },
  "spending": [
    {
      "service": "x402-pastebin",
      "endpoint": "POST /paste",
      "amount_usdc": 0.01,
      "description": "Full report stored on x402-pastebin"
    }
  ],
  "total_spent_usdc": 0.01
}
```

## On-Chain Artifacts

Every analysis produces verifiable on-chain evidence:

| Artifact | Chain | What It Proves |
|----------|-------|---------------|
| **USDC payment tx** (x402-pastebin) | Base mainnet | Agent paid for report storage |
| **USDC payment tx** (x402-timecapsule) | Base mainnet | Agent paid for time-locked disclosure |
| **Paste** | pastebin.0000402.xyz | Full report stored as plain text, retrievable by token |

Each analysis generates 1-2 on-chain USDC transactions. The verdict is returned directly in the API response. A reviewer can verify the agent's spending trail without accessing the sensitive underlying data.

## Tech Stack

| Component | Role | Why |
|-----------|------|-----|
| **Venice AI** | Private inference (Qwen3-235B) | No-data-retention — core privacy guarantee |
| **x402-pastebin** | Report storage | Plain text paste, retrievable by token |
| **x402-timecapsule** | Delayed disclosure | Time-locked content until future date |
| **x402 protocol** | Agent payments | USDC micropayments on Base, no API keys |
| **FastAPI** | Service framework | Async, typed, OpenAPI docs |
| **Etherscan V2 API** | Ethereum on-chain data | Free tier for Ethereum mainnet |
| **Blockscout API** | Base on-chain data | Free, no API key needed |
| **DeFi Llama / Snapshot** | Protocol data | TVL, governance proposals |

## Deployment

Deploy with Docker:

```bash
docker build -t veiled-oracle .
docker run -d -p 32301:8000 \
  --restart unless-stopped \
  --name veiled-oracle \
  --env-file .env \
  veiled-oracle
```

Configure environment variables in `.env` (see `.env.example` for reference).

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VENICE_API_KEY` | Yes | Venice AI API key |
| `VENICE_MODEL` | No | Model to use (default: `qwen3-235b-a22b-instruct-2507`) |
| `WALLET_ADDRESS` | Yes | Agent's wallet address — receives x402 payments from callers |
| `AGENT_PRIVATE_KEY` | Yes | Agent wallet private key for signing outgoing x402 payments |
| `CDP_API_KEY_ID` | Yes | Coinbase Developer Platform key ID (enables x402 payment gate) |
| `CDP_API_KEY_SECRET` | Yes | Coinbase Developer Platform key secret |
| `ANALYZE_PRICE_USDC` | No | Price callers pay per `/analyze` call (default: `0.10`) |
| `NETWORK` | No | `base` (default) or `base-sepolia` |
| `MAX_SPEND_PER_ANALYSIS` | No | Max USDC the agent spends downstream per analysis (default: `0.50`) |
| `MAX_TOTAL_SPEND` | No | Total downstream USDC budget (default: `10.00`) |
| `ETHERSCAN_API_KEY` | No | Etherscan V2 API key for Ethereum data (Base uses Blockscout, no key needed) |
| `RPC_URL` | No | Base RPC endpoint |

**Note:** `WALLET_ADDRESS`, `CDP_API_KEY_ID`, and `CDP_API_KEY_SECRET` are all required — the app refuses to start without them to prevent unprotected public exposure.

## x402 Value Loop

Veiled Oracle is both an x402 **consumer** (pays downstream services) and an x402 **provider** (charges callers). This creates a self-sustaining value loop:

| Direction | Service | Cost | Description |
|-----------|---------|------|-------------|
| **Incoming** | `/analyze` (this API) | $0.10 USDC | Callers pay to use the analysis service |
| **Outgoing** | x402-pastebin | $0.01 USDC | Agent pays to store full reports |
| **Outgoing** | x402-timecapsule | $0.05 USDC | Agent pays to seal reports for delayed disclosure |

**Net per analysis:** agent earns $0.10, spends up to $0.06 downstream → $0.04+ margin per call.

Additional x402 services available at https://0000402.xyz for extending the agent's capabilities.

## License

MIT

## Links

- x402 Collections: https://0000402.xyz
- Omniacs DAO: https://omniacsdao.xyz
- Venice AI: https://venice.ai
- x402 Protocol: https://github.com/coinbase/x402
- Synthesis Hackathon: https://synthesis.devfolio.co
