"""
MEDRESOLVE AI — FastAPI Application
RESTful API for the drug safety intelligence platform.
Drug-only system — guideline endpoints removed; risk report and chat endpoints added.

Key additions vs original:
- RetrievedChunkResponse: exposes chunk details and relevance scores to frontend
- retrieved_chunks in both ChatResponse and RiskReportResponse
- patient_profile_summary in RiskReportResponse
- Updated PatientProfile schema example with new fields
"""

from __future__ import annotations
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from medresolve.config import get_settings
from medresolve.agents.graph import run_query, run_risk_report
from medresolve.models import StructuredResponse, PatientProfile

logger = structlog.get_logger(__name__)
settings = get_settings()

# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="MEDRESOLVE AI",
    description="Personalized Drug Safety Intelligence Platform",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Schemas ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    conversation_history: Optional[list[dict]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the contraindications of lisinopril in patients with renal impairment?",
                "conversation_history": [],
            }
        }


class RiskReportRequest(BaseModel):
    patient_profile: PatientProfile
    additional_query: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "patient_profile": {
                    "full_name": "Jane Doe",
                    "date_of_birth": "1985-03-15",
                    "gender": "female",
                    "blood_type": "A+",
                    "height_cm": 165.0,
                    "weight_kg": 70.0,
                    "target_drug": "lisinopril",
                    "target_drug_id": "lisinopril",
                    "target_drugs": ["lisinopril"],
                    "chronic_conditions": ["hypertension"],
                    "comorbidities": ["renal_impairment", "diabetes"],
                    "patient_factors": ["elderly"],
                    "current_medications": ["metformin"],
                    "allergies": [],
                    "pregnancy_trimester": None,
                    "kidney_function": "eGFR 30-60",
                },
                "additional_query": "",
            }
        }


class RetrievedChunkResponse(BaseModel):
    """Represents a single retrieved evidence chunk with its relevance score."""
    chunk_id: str
    drug_name: str
    section_type: str
    relevance_score: float
    content_preview: str          # First 500 chars of chunk content
    target_patient_factors: list[str]
    has_boxed_warning: bool
    has_contraindications: bool


class ChatResponse(BaseModel):
    success: bool
    query: str
    query_category: str
    interaction_mode: str
    clinical_context_summary: str
    detected_drugs: list[str]
    detected_diseases: list[str]
    main_response: str
    key_points: list[str]
    key_warnings: list[str]
    citations: list[str]
    evidence_quality: str
    evidence_limitations: list[str]
    disclaimer: str
    is_refused: bool
    refusal_reason: str
    # NEW: retrieved chunks with scores
    retrieved_chunks: list[RetrievedChunkResponse]
    execution_trace_summary: dict


class RiskFindingResponse(BaseModel):
    patient_factor: str
    tier: str
    summary: str
    rationale: str
    exact_quote: str
    citations: list[str]
    is_deterministic: bool


class DrugOverviewResponse(BaseModel):
    drug_name: str
    drug_class: str
    primary_indication: str
    mechanism: str
    citations: list[str]


class RiskReportResponse(BaseModel):
    success: bool
    query: str
    interaction_mode: str
    detected_drugs: list[str]
    risk_findings: list[RiskFindingResponse]
    drug_overview: Optional[DrugOverviewResponse]
    main_response: str
    evidence_quality: str
    evidence_limitations: list[str]
    disclaimer: str
    is_refused: bool
    refusal_reason: str
    # NEW: retrieved chunks with scores
    retrieved_chunks: list[RetrievedChunkResponse]
    # NEW: submitted patient profile summary
    patient_profile_summary: dict
    execution_trace_summary: dict


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _serialize_retrieved_chunks(response: StructuredResponse) -> list[RetrievedChunkResponse]:
    """Convert retrieved EvidenceChunk objects to API response format."""
    chunks_out = []
    for chunk in response.retrieved_evidence:
        chunks_out.append(RetrievedChunkResponse(
            chunk_id=chunk.chunk_id,
            drug_name=chunk.drug_name or "Unknown",
            section_type=(chunk.section_type or "General").replace("_", " ").title(),
            relevance_score=round(chunk.score, 4),
            content_preview=chunk.content[:500],
            target_patient_factors=chunk.target_patient_factors,
            has_boxed_warning=chunk.has_boxed_warning,
            has_contraindications=chunk.has_contraindications,
        ))
    return chunks_out


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "MEDRESOLVE AI", "version": "3.0.0"}


@app.post("/query", response_model=ChatResponse)
async def query_chat(request: ChatRequest):
    """
    Chat-mode drug Q&A endpoint.
    Ask any drug safety question and get a grounded, cited response
    with full evidence traceability.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if len(request.query) > settings.max_query_length:
        raise HTTPException(
            status_code=400,
            detail=f"Query too long. Maximum {settings.max_query_length} characters.",
        )

    try:
        logger.info("api_chat_query", query=request.query[:100])
        final_state = run_query(
            query=request.query.strip(),
            conversation_history=request.conversation_history,
        )

        response: StructuredResponse = final_state.get("final_response")
        if not response:
            raise ValueError("Pipeline produced no response")

        trace = response.execution_trace
        trace_summary = {}
        if trace:
            trace_summary = {
                "query_category": trace.query_category,
                "interaction_mode": trace.interaction_mode,
                "processing_steps": trace.processing_steps,
                "drug_chunks_retrieved": trace.drug_chunks_retrieved,
                "drug_sources": trace.drug_sources_used,
                "total_citations": trace.total_claims,
                "valid_citations": trace.grounded_claims,
                "invalid_citations": trace.ungrounded_claims,
                "safety_decision": trace.safety_decision,
                "reretrieval_attempted": trace.reretrieval_attempted,
            }

        return ChatResponse(
            success=True,
            query=response.query,
            query_category=response.query_category,
            interaction_mode=response.interaction_mode,
            clinical_context_summary=response.clinical_context_summary,
            detected_drugs=response.detected_drugs,
            detected_diseases=response.detected_diseases,
            main_response=response.main_response,
            key_points=response.key_points,
            key_warnings=response.key_warnings,
            citations=response.citations,
            evidence_quality=response.evidence_quality,
            evidence_limitations=response.evidence_limitations,
            disclaimer=response.disclaimer,
            is_refused=response.is_refused,
            refusal_reason=response.refusal_reason,
            retrieved_chunks=_serialize_retrieved_chunks(response),
            execution_trace_summary=trace_summary,
        )

    except Exception as e:
        logger.error("api_chat_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/risk-report", response_model=RiskReportResponse)
async def generate_risk_report(request: RiskReportRequest):
    """
    Form-based personalized drug risk report.
    Submit a patient profile (drug + comorbidities + patient factors) and receive
    tiered risk findings (🔴 High / 🟠 Moderate / 🟢 Safe / ⚪ No Data)
    grounded in the drug KB with full evidence traceability.
    """
    if not request.patient_profile.target_drug:
        raise HTTPException(status_code=400, detail="patient_profile.target_drug is required")

    try:
        logger.info("api_risk_report", drug=request.patient_profile.target_drug)
        final_state = run_risk_report(
            patient_profile=request.patient_profile,
            additional_query=request.additional_query or "",
        )

        response: StructuredResponse = final_state.get("final_response")
        if not response:
            raise ValueError("Pipeline produced no response")

        trace = response.execution_trace
        trace_summary = {}
        if trace:
            trace_summary = {
                "processing_steps": trace.processing_steps,
                "drug_chunks_retrieved": trace.drug_chunks_retrieved,
                "drug_sources": trace.drug_sources_used,
                "risk_findings_count": trace.risk_findings_count,
                "valid_citations": trace.grounded_claims,
                "invalid_citations": trace.ungrounded_claims,
                "safety_decision": trace.safety_decision,
                "reretrieval_attempted": trace.reretrieval_attempted,
            }

        # Serialize risk findings
        risk_findings_out = [
            RiskFindingResponse(
                patient_factor=f.patient_factor,
                tier=f.tier.value,
                summary=f.summary,
                rationale=f.rationale,
                exact_quote=f.exact_quote,
                citations=[c.citation_str() for c in f.source_chunks],
                is_deterministic=f.is_deterministic,
            )
            for f in response.risk_findings
        ]

        # Serialize drug overview
        drug_overview_out = None
        if response.drug_overview:
            ov = response.drug_overview
            drug_overview_out = DrugOverviewResponse(
                drug_name=ov.drug_name,
                drug_class=ov.drug_class,
                primary_indication=ov.primary_indication,
                mechanism=ov.mechanism,
                citations=[c.citation_str() for c in ov.source_chunks],
            )

        return RiskReportResponse(
            success=True,
            query=response.query,
            interaction_mode=response.interaction_mode,
            detected_drugs=response.detected_drugs,
            risk_findings=risk_findings_out,
            drug_overview=drug_overview_out,
            main_response=response.main_response,
            evidence_quality=response.evidence_quality,
            evidence_limitations=response.evidence_limitations,
            disclaimer=response.disclaimer,
            is_refused=response.is_refused,
            refusal_reason=response.refusal_reason,
            retrieved_chunks=_serialize_retrieved_chunks(response),
            patient_profile_summary=response.patient_profile_summary,
            execution_trace_summary=trace_summary,
        )

    except Exception as e:
        logger.error("api_risk_report_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.get("/drugs")
async def list_drugs():
    """
    List all drugs available in the knowledge base.
    Returns drug IDs, names, and tier classification for use in the risk report form.
    """
    from medresolve.ingestion.drug_normalizer import DRUG_ALIASES, CLINICAL_RELEVANCE
    drugs = []
    for drug_id, aliases in DRUG_ALIASES.items():
        drugs.append({
            "drug_id": drug_id,
            "drug_name": aliases[0].title() if aliases else drug_id.replace("_", " ").title(),
            "aliases": aliases,
            "tier": CLINICAL_RELEVANCE.get(drug_id, "unknown"),
        })
    return {"drugs": drugs, "total": len(drugs)}


@app.post("/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks, force_rebuild: bool = False):
    """Trigger drug knowledge base ingestion in the background."""
    from medresolve.ingestion.pipeline import MedResolveIngestionPipeline

    def run_ingestion():
        pipeline = MedResolveIngestionPipeline()
        pipeline.run(force_rebuild=force_rebuild)

    background_tasks.add_task(run_ingestion)
    return {"message": "Drug knowledge base ingestion started in background", "force_rebuild": force_rebuild}


@app.get("/status")
async def get_status():
    """Get knowledge base status."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    try:
        client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        drug_collection = client.get_or_create_collection(settings.chroma_drug_collection)

        return {
            "drug_chunks": drug_collection.count(),
            "chroma_db_path": str(settings.chroma_persist_dir),
            "embedding_model": settings.embedding_model,
            "llm_model": settings.gemini_model,
            "system_version": "3.0.0 (drug-only, rebuilt)",
            "llm_calls_per_request": "2 (chat) or 3 (risk_report)",
            "reranker_score_threshold": settings.reranker_score_threshold,
        }
    except Exception as e:
        return {"error": str(e)}
