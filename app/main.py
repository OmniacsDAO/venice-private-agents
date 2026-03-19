"""
Veiled Oracle — Private Intelligence, Public Verdicts.

A request-driven agent that uses Venice AI's no-data-retention inference to
analyze sensitive on-chain data privately, then produces trustworthy public
outputs via x402-powered services on Base:

  Private cognition (Venice)  →  Public action (x402 on Base)
  ─────────────────────────      ─────────────────────────────
  Sensitive data analysis        Public verdicts (API response)
  No-data-retention inference    Full reports on x402-pastebin
  Zero prompt logging            On-chain payment receipts
  Confidential reasoning         Time-locked disclosures

Every action the agent takes is paid for via x402 USDC micropayments,
creating an immutable audit trail on Base — without revealing what was
analyzed.

The /analyze endpoint is itself x402-gated: callers pay a USDC fee to use
the service. This payment covers the agent's downstream x402 costs (pastebin,
timecapsule) and Venice inference. The agent earns revenue from callers and
spends on downstream services — a self-sustaining x402 value loop.

Built for the Synthesis Hackathon 2026 — Venice "Private Agents, Trusted
Actions" track.

Architecture:
                    x402 payment
  ┌──────────┐    (caller pays)    ┌──────────────┐     ┌────────────────┐
  │  Caller  │────────────────────▶│  Veiled      │────▶│  Venice AI     │
  │  (agent  │   USDC on Base      │  Oracle      │     │  (private      │
  │  or user)│◀────────────────────│  (this API)  │     │   inference)   │
  └──────────┘   verdict + report  └──────┬───────┘     └────────────────┘
                                          │  x402 payments
                                          │  (agent pays)
                                   ┌──────▼───────┐
                                   │ x402 Services │
                                   │  Pastebin     │
                                   │  Timecapsule  │
                                   └──────────────┘
"""

import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from cdp.auth.utils.jwt import generate_jwt, JwtOptions
from x402.http import HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer
from x402.extensions.bazaar import declare_discovery_extension, OutputConfig

from app.chain_data import fetch_data_for_analysis, summarize_data_used
from app.models import (
    AnalysisRequest,
    AnalysisResponse,
    AgentStatusResponse,
    ReportRef,
    HealthResponse,
    SpendingRecord,
    TimeCapsuleRef,
    VerdictOutput,
    VerdictSeverity,
)
from app.spending import SpendingLimitExceeded, get_ledger
from app.venice_client import run_private_analysis
from app.x402_services import store_report, seal_report

load_dotenv()

# ── Configuration ─────────────────────────────────────────

NETWORK = os.getenv("NETWORK", "base")
VENICE_MODEL = os.getenv("VENICE_MODEL", "qwen3-235b-a22b-instruct-2507")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")

CDP_API_KEY_ID = os.getenv("CDP_API_KEY_ID")
CDP_API_KEY_SECRET = os.getenv("CDP_API_KEY_SECRET")

# Price callers pay to use /analyze (covers downstream x402 + Venice costs)
ANALYZE_PRICE_USDC = float(os.getenv("ANALYZE_PRICE_USDC", "0.10"))
ANALYZE_PRICE_DISPLAY = f"${ANALYZE_PRICE_USDC:.2f}"

# ── Network Configuration ────────────────────────────────

NETWORKS = {
    "base": {
        "chain_id": 8453,
        "caip2": "eip155:8453",
        "usdc": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        "label": "Base Mainnet",
    },
    "base-sepolia": {
        "chain_id": 84532,
        "caip2": "eip155:84532",
        "usdc": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "label": "Base Sepolia",
    },
}

if NETWORK not in NETWORKS:
    raise RuntimeError(f"Unsupported NETWORK: {NETWORK}. Use 'base' or 'base-sepolia'.")

CFG = NETWORKS[NETWORK]
TESTNET = NETWORK != "base"

# ── FastAPI App ───────────────────────────────────────────

app = FastAPI(
    title="Veiled Oracle",
    description=(
        "Private intelligence, public verdicts. "
        "Venice AI private inference + x402 on-chain actions. "
        f"Callers pay {ANALYZE_PRICE_DISPLAY} USDC via x402 to use /analyze."
    ),
    version="1.0.0",
)

templates = Jinja2Templates(directory="app/templates")

# ── x402 Payment Gate ────────────────────────────────────
#
# The /analyze endpoint is protected by x402 payment middleware.
# Callers must sign a USDC payment before the request is processed.
# This serves two purposes:
#   1. Prevents abuse — no free calls to an expensive endpoint
#   2. Creates a self-sustaining value loop — the agent earns from
#      callers and spends on downstream x402 services
#
# Free endpoints (/, /health, /status) are NOT gated.

if WALLET_ADDRESS and CDP_API_KEY_ID and CDP_API_KEY_SECRET:
    def _create_cdp_headers() -> dict[str, dict[str, str]]:
        """Generate CDP JWT auth headers for x402 facilitator."""
        base_path = "/platform/v2/x402"

        def _jwt(method: str, path: str) -> str:
            return generate_jwt(
                JwtOptions(
                    api_key_id=CDP_API_KEY_ID,
                    api_key_secret=CDP_API_KEY_SECRET,
                    request_method=method,
                    request_host="api.cdp.coinbase.com",
                    request_path=f"{base_path}{path}",
                )
            )

        return {
            "verify": {"Authorization": f"Bearer {_jwt('POST', '/verify')}"},
            "settle": {"Authorization": f"Bearer {_jwt('POST', '/settle')}"},
            "supported": {"Authorization": f"Bearer {_jwt('GET', '/supported')}"},
        }

    facilitator = HTTPFacilitatorClient({
        "url": "https://api.cdp.coinbase.com/platform/v2/x402",
        "create_headers": _create_cdp_headers,
    })
    resource_server = x402ResourceServer(facilitator)
    resource_server.register(CFG["caip2"], ExactEvmServerScheme())

    x402_routes = {
        "POST /analyze": RouteConfig(
            accepts=[
                PaymentOption(
                    scheme="exact",
                    pay_to=WALLET_ADDRESS,
                    price=ANALYZE_PRICE_DISPLAY,
                    network=CFG["caip2"],
                ),
            ],
            description=(
                f"Pay {ANALYZE_PRICE_DISPLAY} USDC to run a private analysis via "
                f"Venice AI (no-data-retention). Report stored on x402-pastebin. "
                f"Analysis types: treasury, governance, risk, due_diligence. "
                f"Network: {CFG['label']}."
            ),
            mime_type="application/json",
            extensions={
                **declare_discovery_extension(
                    input={
                        "analysis_type": "treasury",
                        "target": "0x1234...",
                        "publish_verdict": True,
                    },
                    input_schema={
                        "type": "object",
                        "properties": {
                            "analysis_type": {
                                "type": "string",
                                "enum": ["treasury", "governance", "risk", "due_diligence"],
                                "description": "Type of analysis to perform",
                            },
                            "target": {
                                "type": "string",
                                "description": "Address or protocol name to analyze",
                            },
                            "context": {
                                "type": "string",
                                "description": "Optional private context (sent to Venice only, never stored)",
                            },
                            "publish_verdict": {"type": "boolean", "default": True},
                            "seal_until": {
                                "type": "string",
                                "description": "ISO 8601 timestamp for time-locked disclosure (optional)",
                            },
                        },
                        "required": ["analysis_type", "target"],
                    },
                    body_type="json",
                    output=OutputConfig(
                        example={
                            "verdict": {"severity": "healthy", "summary": "Treasury is well-diversified..."},
                            "report": {"retrieval_url": "https://pastebin.0000402.xyz/paste/..."},
                        }
                    ),
                ),
            },
        ),
    }

    app.add_middleware(PaymentMiddlewareASGI, routes=x402_routes, server=resource_server)
else:
    _missing = [k for k, v in {
        "WALLET_ADDRESS": WALLET_ADDRESS,
        "CDP_API_KEY_ID": CDP_API_KEY_ID,
        "CDP_API_KEY_SECRET": CDP_API_KEY_SECRET,
    }.items() if not v]
    raise RuntimeError(
        f"x402 payment gate cannot start — missing: {', '.join(_missing)}. "
        f"Without the payment gate, /analyze is unprotected and would spend "
        f"operator funds on every request. Set all three env vars to proceed."
    )


# ── Routes ────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Human-readable landing page."""
    ledger = get_ledger()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "venice_model": VENICE_MODEL,
            "network": CFG["label"],
            "max_per_analysis": ledger.max_per_analysis,
            "max_total": ledger.max_total,
            "total_spent": ledger.total_spent,
            "analyses_completed": ledger.analyses_completed,
            "x402_enabled": True,
            "analyze_price": ANALYZE_PRICE_USDC,
            "wallet_address": WALLET_ADDRESS,
        },
    )


@app.get("/health")
async def health() -> HealthResponse:
    """Health check with agent configuration."""
    ledger = get_ledger()
    return HealthResponse(
        venice_model=VENICE_MODEL,
        network=NETWORK,
        spending_limit_per_analysis=ledger.max_per_analysis,
        total_budget_remaining=ledger.remaining,
    )


@app.get("/status")
async def agent_status() -> AgentStatusResponse:
    """Current agent spending status and statistics."""
    ledger = get_ledger()
    return AgentStatusResponse(
        total_spent_usdc=ledger.total_spent,
        budget_remaining_usdc=ledger.remaining,
        max_per_analysis_usdc=ledger.max_per_analysis,
        analyses_completed=ledger.analyses_completed,
        verdicts_published=ledger.verdicts_published,
        reports_stored=ledger.reports_stored,
    )


@app.post("/analyze")
async def analyze(req: AnalysisRequest) -> AnalysisResponse:
    """
    Run a private analysis and produce public outputs.

    Flow:
    1. Fetch public on-chain data for the target
    2. Send data + private context to Venice (no-data-retention)
    3. Venice returns verdict (public) + report (private)
    4. Verdict returned directly in the API response
    5. Store report via x402-pastebin (plain text)
    6. Optionally seal report in x402-timecapsule

    Privacy guarantees:
    - Raw data and reasoning processed ONLY by Venice (no retention)
    - Private context is never stored anywhere
    - Public verdict contains ONLY the conclusion
    - All payments are x402 USDC micropayments on Base
    """
    ledger = get_ledger()
    spending: list[SpendingRecord] = []
    total_cost = 0.0

    # Estimate cost and check budget
    estimated_cost = 0.01  # pastebin paste
    if req.seal_until:
        estimated_cost += 0.05  # time capsule

    if estimated_cost > ledger.max_per_analysis:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estimated cost ${estimated_cost:.2f} exceeds "
                f"per-analysis limit ${ledger.max_per_analysis:.2f}"
            ),
        )
    if not ledger.can_spend(estimated_cost):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Budget exhausted. Remaining: ${ledger.remaining:.2f}, "
                f"needed: ${estimated_cost:.2f}. "
                f"Human operator must increase MAX_TOTAL_SPEND."
            ),
        )

    analysis_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # ── Step 1: Fetch public on-chain data ────────────────

    chain_data = await fetch_data_for_analysis(
        req.analysis_type.value, req.target
    )

    # ── Step 2: Private analysis via Venice ───────────────
    # This is where privacy happens. The raw data, private context,
    # and all reasoning occur inside Venice's no-data-retention
    # inference pipeline. Nothing is stored.

    analysis_result = await run_private_analysis(
        analysis_type=req.analysis_type.value,
        target=req.target,
        on_chain_data=chain_data,
        private_context=req.context,  # sent to Venice only, never stored
    )

    severity = analysis_result.get("severity", "caution")
    verdict_summary = analysis_result.get(
        "verdict_summary",
        f"Analysis of {req.target} completed.",
    )
    report = analysis_result.get("report", {})

    # ── Step 3: Build verdict (returned directly in API response) ─────

    verdict = VerdictOutput(
        severity=VerdictSeverity(severity),
        summary=verdict_summary,
    )

    if req.publish_verdict:
        ledger.record_verdict()

    # ── Step 4: Store full report via x402-pastebin ──────

    report_ref = None
    paste_result = await store_report(report=report)
    report_ref = ReportRef(
        pastebin_token=paste_result.get("pastebin_token"),
        retrieval_url=paste_result.get("retrieval_url"),
        burn_after_reading=False,
    )
    cost = paste_result.get("cost_usdc", 0)
    if cost > 0:
        ledger.record_spend(cost)
        ledger.record_stored()
        total_cost += cost
        spending.append(
            SpendingRecord(
                service="x402-pastebin",
                endpoint="POST /paste",
                amount_usdc=cost,
                description="Full report stored on x402-pastebin",
            )
        )

    # ── Step 5: Seal in time capsule (optional) ───────────

    capsule_ref = None
    if req.seal_until:
        seal_result = await seal_report(
            report=report,
            unlock_at=req.seal_until,
            label=f"Veiled Oracle — {req.analysis_type.value} analysis of {req.target}",
        )
        capsule_ref = TimeCapsuleRef(
            capsule_token=seal_result.get("capsule_token"),
            unlock_at=seal_result.get("unlock_at"),
            status_url=seal_result.get("status_url"),
        )
        cost = seal_result.get("cost_usdc", 0)
        if cost > 0:
            ledger.record_spend(cost)
            total_cost += cost
            spending.append(
                SpendingRecord(
                    service="x402-timecapsule",
                    endpoint="POST /seal",
                    amount_usdc=cost,
                    description="Sealed full report in time capsule for delayed disclosure",
                )
            )

    ledger.record_analysis()

    return AnalysisResponse(
        analysis_id=analysis_id,
        analysis_type=req.analysis_type,
        target=req.target,
        timestamp=timestamp,
        verdict=verdict,
        data_used=summarize_data_used(req.analysis_type.value, chain_data),
        report=report_ref,
        time_capsule=capsule_ref,
        spending=spending,
        total_spent_usdc=total_cost,
    )


# ── Run ───────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
