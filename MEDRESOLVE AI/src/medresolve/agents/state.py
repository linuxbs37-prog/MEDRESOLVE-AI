"""
MEDRESOLVE AI — LangGraph State Schema
Central state object that flows through all graph nodes.
Drug-only personalized system.
"""

from __future__ import annotations
from typing import Annotated, Optional
from typing_extensions import TypedDict
import operator

from medresolve.models import (
    ClinicalContext,
    RetrievalPlan,
    EvidenceChunk,
    GroundedClaim,
    SafetyAssessment,
    StructuredResponse,
    ExecutionTrace,
    QueryCategory,
    PatientProfile,
    RiskFinding,
    DrugOverview,
)


class MedResolveState(TypedDict):
    """
    Central state for the MEDRESOLVE AI LangGraph workflow.
    All nodes read from and write to this state.
    """
    # ── Input ─────────────────────────────────────────────────────────────────
    query: str
    conversation_history: list[dict]

    # ── Interaction Mode ──────────────────────────────────────────────────────
    # "risk_report" for form-based personalized reports
    # "chat_query" for multi-turn conversational Q&A
    interaction_mode: str

    # ── Patient Profile (Risk Report mode only) ───────────────────────────────
    patient_profile: Optional[PatientProfile]

    # ── Clinical Context (extracted in classify node) ─────────────────────────
    clinical_context: Optional[ClinicalContext]
    query_category: str   # QueryCategory enum value as string

    # ── Retrieval Plan ────────────────────────────────────────────────────────
    retrieval_plan: Optional[RetrievalPlan]

    # ── Retrieved Evidence ────────────────────────────────────────────────────
    drug_evidence: list[EvidenceChunk]

    # ── Retrieval Sufficiency ─────────────────────────────────────────────────
    evidence_sufficient: bool
    sufficiency_check_count: int   # Prevent infinite loops

    # ── Risk Assessment (Risk Report mode only) ───────────────────────────────
    risk_findings: list[RiskFinding]
    drug_overview: Optional[DrugOverview]

    # ── Draft & Grounding ─────────────────────────────────────────────────────
    draft_response: str
    grounded_claims: list[GroundedClaim]

    # ── Safety ────────────────────────────────────────────────────────────────
    safety_assessment: Optional[SafetyAssessment]

    # ── Final Output ──────────────────────────────────────────────────────────
    final_response: Optional[StructuredResponse]

    # ── Execution Trace ───────────────────────────────────────────────────────
    execution_trace: ExecutionTrace

    # ── Error Handling ────────────────────────────────────────────────────────
    error_message: str
