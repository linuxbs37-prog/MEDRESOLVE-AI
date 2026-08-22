"""
MEDRESOLVE AI — LangGraph Workflow Definition
Drug-only personalized system — simplified 6-node graph.

New graph (down from 9 nodes / 6 LLM calls → 5 nodes / 2-3 LLM calls):
START → classify_and_extract
  ├─ out_of_scope → END
  ├─ ambiguous → END
  ├─ safety_refusal → END
  └─ (all others) → retrieve_drug_evidence → verify_and_retrieve
       └─ (risk_report) → assess_risk → synthesize_response → ground_and_format → END
       └─ (chat)        → synthesize_response → ground_and_format → END

LLM calls:
  - classify_and_extract: 1 call (chat mode only; 0 for form-based)
  - assess_risk: 1 call (risk_report mode only)
  - synthesize_response: 1 call (always)
  Total: 2-3 LLM calls vs original 6
"""

from __future__ import annotations
from typing import Literal
from functools import lru_cache

from langgraph.graph import StateGraph, START, END
import structlog

from medresolve.agents.state import MedResolveState
from medresolve.agents.nodes import (
    classify_and_extract,
    retrieve_drug_evidence,
    verify_and_retrieve,
    assess_risk,
    synthesize_response,
    ground_and_format,
    out_of_scope_response,
    ambiguous_response,
)
from medresolve.models import (
    QueryCategory, ExecutionTrace, InteractionMode,
    PatientProfile, StructuredResponse, SafetyAssessment,
    SafetyDecision,
)

logger = structlog.get_logger(__name__)


# ─── Routing Functions ────────────────────────────────────────────────────────

def route_after_classify(
    state: MedResolveState,
) -> Literal["retrieve_drug_evidence", "out_of_scope_response", "ambiguous_response", "safety_refusal"]:
    """Route after query classification."""
    category = state.get("query_category", "")

    if category == QueryCategory.OUT_OF_SCOPE:
        return "out_of_scope_response"
    elif category == QueryCategory.UNSAFE_REQUEST:
        return "safety_refusal"
    elif category == QueryCategory.AMBIGUOUS:
        return "ambiguous_response"
    else:
        return "retrieve_drug_evidence"


def route_after_verify(
    state: MedResolveState,
) -> Literal["assess_risk", "synthesize_response"]:
    """
    Route after evidence verification — decide if risk assessment is needed.
    Risk Report mode → assess_risk → synthesize_response
    Chat mode → synthesize_response directly
    """
    interaction_mode = state.get("interaction_mode", InteractionMode.CHAT_QUERY.value)

    if interaction_mode == InteractionMode.RISK_REPORT.value:
        return "assess_risk"
    return "synthesize_response"


def safety_refusal_node(state: MedResolveState) -> MedResolveState:
    """Handle unsafe requests."""
    from medresolve.agents.prompts import SAFETY_REFUSAL_TEMPLATE, STANDARD_DISCLAIMER

    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("safety_refusal")

    msg = SAFETY_REFUSAL_TEMPLATE.format(request_type="a personal diagnosis or prescription")

    response = StructuredResponse(
        query=state["query"],
        query_category=QueryCategory.UNSAFE_REQUEST.value,
        main_response=msg,
        is_refused=True,
        refusal_reason="Personalized medical advice request detected",
        safety_assessment=SafetyAssessment(
            decision=SafetyDecision.REFUSED,
            reasons=["Personalized medical advice requested"],
            disclaimer_required=True,
        ),
        disclaimer=STANDARD_DISCLAIMER,
        execution_trace=trace,
    )
    return {**state, "final_response": response, "execution_trace": trace}


# ─── Graph Construction ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def build_graph():
    """
    Build and compile the MEDRESOLVE AI LangGraph workflow.
    Simplified 6-node graph with 2-3 LLM calls (vs original 9-node, 6-call graph).
    Cached — call this to get the compiled graph.
    """
    builder = StateGraph(MedResolveState)

    # ── Add all nodes ─────────────────────────────────────────────────────────
    builder.add_node("classify_and_extract", classify_and_extract)
    builder.add_node("retrieve_drug_evidence", retrieve_drug_evidence)   # No LLM
    builder.add_node("verify_and_retrieve", verify_and_retrieve)          # No LLM
    builder.add_node("assess_risk", assess_risk)                          # LLM (risk_report only)
    builder.add_node("synthesize_response", synthesize_response)          # LLM
    builder.add_node("ground_and_format", ground_and_format)              # No LLM
    builder.add_node("out_of_scope_response", out_of_scope_response)
    builder.add_node("ambiguous_response", ambiguous_response)
    builder.add_node("safety_refusal", safety_refusal_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    # Entry
    builder.add_edge(START, "classify_and_extract")

    # Routing after classification
    builder.add_conditional_edges(
        "classify_and_extract",
        route_after_classify,
        {
            "retrieve_drug_evidence": "retrieve_drug_evidence",
            "out_of_scope_response": "out_of_scope_response",
            "ambiguous_response": "ambiguous_response",
            "safety_refusal": "safety_refusal",
        },
    )

    # Retrieval pipeline
    builder.add_edge("retrieve_drug_evidence", "verify_and_retrieve")

    # Mode-aware routing after verification
    builder.add_conditional_edges(
        "verify_and_retrieve",
        route_after_verify,
        {
            "assess_risk": "assess_risk",
            "synthesize_response": "synthesize_response",
        },
    )

    # Risk assessment → synthesis (risk report mode)
    builder.add_edge("assess_risk", "synthesize_response")

    # Synthesis → grounding+formatting → end
    builder.add_edge("synthesize_response", "ground_and_format")
    builder.add_edge("ground_and_format", END)

    # Terminal nodes
    builder.add_edge("out_of_scope_response", END)
    builder.add_edge("ambiguous_response", END)
    builder.add_edge("safety_refusal", END)

    graph = builder.compile()
    logger.info("langgraph_compiled", nodes=len(builder.nodes))
    return graph


# ─── Entry Points ─────────────────────────────────────────────────────────────

def _build_initial_state(
    query: str,
    conversation_history: list[dict] | None = None,
    interaction_mode: str = InteractionMode.CHAT_QUERY.value,
    patient_profile: PatientProfile | None = None,
) -> MedResolveState:
    """Build clean initial state for a pipeline run."""
    return {
        "query": query,
        "conversation_history": conversation_history or [],
        "interaction_mode": interaction_mode,
        "patient_profile": patient_profile,
        "clinical_context": None,
        "query_category": "",
        "retrieval_plan": None,
        "drug_evidence": [],
        "evidence_sufficient": False,
        "sufficiency_check_count": 0,
        "risk_findings": [],
        "drug_overview": None,
        "draft_response": "",
        "grounded_claims": [],
        "safety_assessment": None,
        "final_response": None,
        "execution_trace": ExecutionTrace(),
        "error_message": "",
    }


def run_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Main entry point for chat-mode Q&A queries.

    Args:
        query: User query string
        conversation_history: Optional list of previous messages

    Returns:
        Final state dict containing 'final_response' (StructuredResponse)
    """
    graph = build_graph()
    initial_state = _build_initial_state(
        query=query,
        conversation_history=conversation_history,
        interaction_mode=InteractionMode.CHAT_QUERY.value,
    )
    logger.info("pipeline_start", mode="chat", query=query[:100])
    final_state = graph.invoke(initial_state)
    logger.info("pipeline_complete", category=final_state.get("query_category", ""))
    return final_state


def run_risk_report(
    patient_profile: PatientProfile,
    additional_query: str = "",
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Entry point for form-based personalized risk report.

    Args:
        patient_profile: Submitted patient profile (drug + comorbidities + factors)
        additional_query: Optional free-text question alongside the form
        conversation_history: Optional prior conversation context

    Returns:
        Final state dict containing 'final_response' with risk_findings + drug_overview
    """
    graph = build_graph()

    # Build query from profile
    factors_str = ", ".join(
        patient_profile.comorbidities + patient_profile.patient_factors
    ) or "no specific conditions noted"
    query = additional_query or (
        f"Personalized risk assessment for {patient_profile.target_drug} "
        f"in a patient with: {factors_str}"
    )

    initial_state = _build_initial_state(
        query=query,
        conversation_history=conversation_history,
        interaction_mode=InteractionMode.RISK_REPORT.value,
        patient_profile=patient_profile,
    )
    logger.info("pipeline_start", mode="risk_report", drug=patient_profile.target_drug)
    final_state = graph.invoke(initial_state)
    logger.info(
        "pipeline_complete",
        findings=len(final_state.get("risk_findings", [])),
    )
    return final_state
