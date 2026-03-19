"""Pydantic models for Veiled Oracle requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AnalysisType(str, Enum):
    TREASURY = "treasury"
    GOVERNANCE = "governance"
    RISK = "risk"
    DUE_DILIGENCE = "due_diligence"


class VerdictSeverity(str, Enum):
    HEALTHY = "healthy"
    CAUTION = "caution"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Requests ──────────────────────────────────────────────


class AnalysisRequest(BaseModel):
    """A request for private analysis with a public verdict."""

    analysis_type: AnalysisType = Field(
        description="Type of analysis to perform"
    )
    target: str = Field(
        description="Target to analyze — an Ethereum address, ENS name, or protocol name"
    )
    context: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Additional private context the agent should consider "
        "(never stored, never logged, sent only to Venice)",
    )
    publish_verdict: bool = Field(
        default=True,
        description="Whether to include the verdict in the API response",
    )
    seal_until: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp — seal the full report in a time capsule "
        "until this date (optional)",
    )


# ── Responses ─────────────────────────────────────────────


class SpendingRecord(BaseModel):
    """A single x402 payment made during analysis."""

    service: str
    endpoint: str
    amount_usdc: float
    description: str


class VerdictOutput(BaseModel):
    """The public verdict — contains NO sensitive data."""

    severity: VerdictSeverity
    summary: str = Field(description="One-line public verdict")


class ReportRef(BaseModel):
    """Reference to the stored full report — no content here."""

    pastebin_token: Optional[str] = None
    retrieval_url: Optional[str] = None
    burn_after_reading: bool = False


class TimeCapsuleRef(BaseModel):
    """Reference to time-locked report."""

    capsule_token: Optional[str] = None
    unlock_at: Optional[str] = None
    status_url: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Complete response from a Veiled Oracle analysis."""

    analysis_id: str
    analysis_type: AnalysisType
    target: str
    timestamp: str
    privacy_guarantee: str = (
        "All raw data and reasoning processed via Venice AI "
        "(no-data-retention inference). Sensitive inputs are never "
        "stored, logged, or persisted by any component in the pipeline."
    )
    verdict: VerdictOutput
    data_used: list[str] = Field(
        default_factory=list,
        description="Summary of on-chain data sources consulted to derive the conclusions",
    )
    report: Optional[ReportRef] = None
    time_capsule: Optional[TimeCapsuleRef] = None
    spending: list[SpendingRecord] = Field(
        default_factory=list,
        description="Itemized x402 payments made during this analysis",
    )
    total_spent_usdc: float = 0.0


class HealthResponse(BaseModel):
    service: str = "veiled-oracle"
    status: str = "healthy"
    version: str = "1.0.0"
    venice_model: str = ""
    privacy: str = "Venice no-data-retention inference"
    network: str = ""
    spending_limit_per_analysis: float = 0.0
    total_budget_remaining: float = 0.0


class AgentStatusResponse(BaseModel):
    """Current agent spending status and configuration."""

    total_spent_usdc: float
    budget_remaining_usdc: float
    max_per_analysis_usdc: float
    analyses_completed: int
    verdicts_published: int
    reports_stored: int
