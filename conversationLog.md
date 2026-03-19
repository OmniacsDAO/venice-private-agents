# Conversation Log — Veiled Oracle

**Agent Harness:** OpenClaw (openclaw)
**Model:** Claude Opus 4.6
**Human:** Omniacs DAO
**Build Period:** 2026-03-16 to 2026-03-19

## Context

We came into Synthesis interested in the intersection of private AI inference and on-chain verifiability. The Venice "Private Agents, Trusted Actions" track caught our attention immediately — the idea that agents can reason over sensitive data without exposure, while still producing trustworthy public outputs, felt like an unsolved and important problem.

We'd been building x402-powered services (pastebin, timecapsule) independently and had been watching Venice AI's no-data-retention offering. The hackathon was the push to wire them together: what if an agent could analyze sensitive treasury data privately and produce public verdicts backed by on-chain payment receipts?

## Day 1 — Architecture and Core Implementation

### Human Direction
- Scoped the core problem: DAOs and protocols need private financial intelligence with public accountability. Treasuries get analyzed by AI tools that store the data — the analysis itself is a leak.
- Set the constraint that Venice must be genuinely load-bearing, not decorative. If you can swap out Venice for any other provider and nothing breaks, the integration isn't real.
- Wanted four analysis types matching the Venice track's example directions: treasury copilots, governance analysts, risk desks, due diligence agents.

### Agent Contributions
- Read the Venice track description and extracted the key design principle: "the layer between private intelligence and public consequence."
- Proposed the "Veiled Oracle" name and the split-output model: Venice returns a public verdict (severity + one sentence, zero sensitive details) and a private report (detailed findings). This directly implements private cognition → public action.
- Designed the full architecture: caller pays via x402 → agent fetches public on-chain data → sends to Venice for private inference → stores report on x402-pastebin → optionally seals in x402-timecapsule → returns verdict to caller.
- Built the initial stack: FastAPI service, Venice client with structured system prompts per analysis type, on-chain data fetching via Etherscan, x402 payment integration for downstream services, spending controls with per-analysis and total budget caps.

### Key Decision: x402 Payment Gate

Early on we debated whether the `/analyze` endpoint should be free or paid. The human pointed out a critical security issue: without a payment gate, anyone who discovers the endpoint can trigger analyses that spend the operator's Venice credits and x402 funds. The agent consumes expensive resources on every call.

We made the x402 payment gate mandatory — the app refuses to start without CDP keys configured. This turns Veiled Oracle from a cost center into a self-sustaining service: callers pay $0.10 USDC per analysis, the agent spends ~$0.06 downstream, netting ~$0.04 margin per call.

### Key Decision: Split Output Model

Each Venice system prompt enforces a strict JSON contract:
- `verdict_summary`: one sentence, no sensitive data, safe to publish
- `report`: detailed findings with risk factors and recommendations

The verdict goes directly in the API response. The full report gets stored on x402-pastebin. This separation is the core privacy guarantee — the public verdict reveals the conclusion without the reasoning, and the private report is stored behind a token that only the caller receives.

## Day 2 — x402 Client Integration and Deployment

### The 402 Dance

First deployment to our remote machine went smoothly — Docker container started, health check passed, homepage loaded. But the first real test from the demo script hit a wall:

```
POST /analyze HTTP/1.1  402 Payment Required
ERROR: 402 response missing payment options
```

The demo.py was trying to manually parse the 402 response body and extract payment options. But x402 has a proper client SDK that handles the full 402 → sign → retry flow automatically.

**Fix:** Rewrote the demo client to use the correct x402 SDK pattern:
```python
client = x402ClientSync()
client.register(caip2, ExactEvmScheme(signer))
session = x402_requests(client)
# session.post() now auto-handles 402 → sign USDC → retry with X-Payment header
```

This was a significant learning moment — the x402 SDK abstracts away the payment negotiation entirely. You don't parse 402 responses manually; you register a signer and let the client handle it.

### The Self-Pay Bug

After fixing the client pattern, the next error was more subtle:

```
Facilitator verify failed (400): invalid_payload
```

We spent time checking SDK version mismatches (server had x402 2.4.0, client had 2.2.0), upgraded the client, same error. Eventually realized the root cause: **the demo was using the same wallet private key as the server**. The x402 facilitator rejects payments where payer and payee are the same address — you can't pay yourself.

**Fix:** Used separate wallet keys for the demo client (payer) and the deployed server (payee). Obvious in hindsight, but the error message from the facilitator didn't make this clear.

## Day 3 — Data Sources and Production Hardening

### Etherscan V1 → V2 Migration

After the first successful end-to-end analysis, we noticed the `data_used` field was showing "No on-chain data available." Checked the container logs:

```
Explorer returned non-success: NOTOK
```

Ran a manual curl test against the Etherscan API and got back:
```json
{"status":"0","message":"NOTOK","result":"You are using a deprecated V1 endpoint, switch to Etherscan API V2"}
```

Etherscan had deprecated their V1 API. Migrated to V2 (`https://api.etherscan.io/v2/api` with `chainid` parameter).

### Etherscan Free Tier Limitations

The V2 migration worked for Ethereum (chainid=1), but querying Base (chainid=8453) returned:

```
Free API access is not supported for this chain. Please upgrade your api plan for full chain coverage.
```

Etherscan's free tier only covers Ethereum mainnet via V2. Rather than paying for an API plan, we switched Base data to **Blockscout** (`base.blockscout.com/api/v2`) — completely free, no API key needed. This actually improved the architecture: we're not locked into a single data provider.

**Final data source setup:**
- Ethereum: Etherscan V2 API (free tier, requires API key)
- Base: Blockscout API (free, no key needed)
- Governance: Snapshot GraphQL (free)
- Protocol metrics: DeFi Llama (free)

### Blockscout Null Token Symbols

First test with Blockscout data caused a crash:

```
TypeError: '<' not supported between instances of 'NoneType' and 'str'
```

Blockscout returns `null` for some token symbols in its token-balances endpoint. The code was sorting token names without handling None values. Fixed by filtering nulls and defaulting to "UNKNOWN" at ingestion.

### Rate Limiting

The human flagged that Etherscan enforces a 3 calls/sec rate limit on the free tier. Added a 0.35-second delay between Etherscan API calls (~2.8 calls/sec, staying safely under the limit). Blockscout has more generous limits so no delay needed there.

### Documentation Consistency

A recurring theme throughout the build: after each code change, documentation would drift. The human caught this multiple times — README still saying "encrypted" after we switched to plain pastebin, index.html showing old API response format, demo.py not reflecting new fields. We did several full-pass documentation audits to keep README, index.html, demo.py, .env.example, and agent.json all consistent with the actual code behavior.

## Design Decisions Summary

1. **Venice is load-bearing** — Without no-data-retention inference, the agent's analysis prompts (containing sensitive financial data) would be stored by the inference provider. The entire privacy promise depends on Venice. Swapping in any other provider breaks the guarantee.

2. **x402 payment gate is mandatory** — The app refuses to start without CDP keys. This prevents unprotected public exposure where anyone could drain the operator's funds. The payment gate also creates the self-sustaining value loop: callers fund the agent's downstream spending.

3. **Split output** — Public verdict (conclusion only) + private report (full findings). The separation ensures the API response is safe to publish while the detailed analysis remains accessible only to the caller.

4. **Dual-chain data** — Querying both Ethereum and Base gives a more complete picture for treasury analysis. Using different providers (Etherscan + Blockscout) avoids single-vendor lock-in.

5. **Budget caps** — `MAX_SPEND_PER_ANALYSIS` and `MAX_TOTAL_SPEND` give the human operator control over the agent's downstream spending. The agent self-enforces and returns 402 when exhausted.

6. **Request-triggered execution** — The agent is not fully autonomous — it doesn't discover targets or schedule its own work. A caller sends a POST to `/analyze`, and the agent autonomously executes the full fetch → analyze → publish pipeline for that request. This is an honest characterization of the execution model.

## What Worked Well

- The x402 SDK's client pattern made payment integration clean — register a signer, and all HTTP calls auto-negotiate payments.
- Venice's OpenAI-compatible API meant we could use the standard OpenAI SDK with just a base_url swap.
- Structured system prompts with explicit JSON contracts gave reliable, parseable output from Venice.
- The self-sustaining value loop (charge callers more than downstream costs) makes the agent economically viable without ongoing operator funding.

## What Was Hard

- The self-pay bug was non-obvious — the facilitator error message didn't indicate that payer === payee was the issue.
- Keeping documentation in sync with code changes across 6+ files required discipline and multiple review passes.
- Etherscan's V1 deprecation and V2 free-tier chain restrictions required pivoting data sources mid-build.
- Blockscout's API has inconsistencies (null token symbols) that required defensive coding.

## Execution Model Note

The agent is request-triggered: a caller sends a POST to `/analyze`, and the agent autonomously executes the full fetch → analyze → publish pipeline for that request. It does not independently discover targets or schedule its own work. The autonomy is within the analysis pipeline, not in self-directed task selection.
