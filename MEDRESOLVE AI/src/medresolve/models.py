"""
MEDRESOLVE AI — Core Data Models
All Pydantic models used across the system.
Drug-only personalized system — guideline components removed.
"""

from __future__ import annotations
import math
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────

class QueryCategory(str, Enum):
    DRUG_ONLY = "drug_only"
    DRUG_DISEASE = "drug_disease"
    MULTI_DISEASE = "multi_disease"
    RISK_REPORT = "risk_report"       # Form-based personalized risk assessment
    CHAT_QUERY = "chat_query"         # Multi-turn conversational drug Q&A
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"
    UNSAFE_REQUEST = "unsafe_request"


class SourceType(str, Enum):
    DRUG_EVIDENCE = "drug_evidence"


class SupportLevel(str, Enum):
    FULLY_SUPPORTED = "fully_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class SafetyDecision(str, Enum):
    SAFE = "safe"
    MODIFIED = "modified"       # Response modified to remove unsafe content
    REFUSED = "refused"         # Request refused entirely
    FLAGGED = "flagged"         # Allowed but with strong warnings


class RiskTier(str, Enum):
    HIGH_WARNING = "high_warning"       # 🔴 — contraindication or boxed warning
    MODERATE_CAUTION = "moderate_caution"  # 🟠 — needs monitoring
    SAFE = "safe"                       # 🟢 — chunk explicitly states safe/appropriate
    NO_DATA = "no_data"                 # ⚪ — no relevant chunk found in KB


class InteractionMode(str, Enum):
    RISK_REPORT = "risk_report"   # Form-based personalized report
    CHAT_QUERY = "chat_query"     # Multi-turn conversational Q&A


# ─── Patient Profile ──────────────────────────────────────────────────────────

class PatientProfile(BaseModel):
    """Form-submitted patient profile for personalized risk assessment."""

    # ── Identity fields (for display, not used in retrieval) ─────────────────
    full_name: str = Field(default="", description="Patient full name")
    date_of_birth: Optional[str] = Field(default=None, description="ISO date string: YYYY-MM-DD")
    gender: Optional[str] = Field(default=None, description="'male' | 'female' | 'other'")
    blood_type: Optional[str] = Field(default=None, description="e.g. 'A+' | 'O-'")
    height_cm: Optional[float] = Field(default=None, description="Height in centimeters")
    weight_kg: Optional[float] = Field(default=None, description="Weight in kilograms")

    # ── Clinical fields (used in retrieval & risk assessment) ─────────────────
    target_drug: str = Field(default="", description="Primary drug being assessed (kept for compat)")
    target_drug_id: str = Field(default="", description="Normalized drug ID (snake_case)")
    target_drugs: list[str] = Field(default_factory=list, description="All drugs being assessed (multi-drug support)")
    chronic_conditions: list[str] = Field(
        default_factory=list,
        description="Chronic medical conditions (separate from comorbidities for UI alignment)",
    )
    comorbidities: list[str] = Field(
        default_factory=list,
        description="e.g. ['renal_impairment', 'diabetes', 'hypertension']",
    )
    patient_factors: list[str] = Field(
        default_factory=list,
        description="e.g. ['pregnancy', 'elderly', 'hepatic_impairment']",
    )
    current_medications: list[str] = Field(
        default_factory=list,
        description="Other drugs the patient is currently taking",
    )
    allergies: list[str] = Field(
        default_factory=list,
        description="Known drug or substance allergies",
    )
    pregnancy_trimester: Optional[str] = Field(
        default=None,
        description="'first' | 'second' | 'third' | None",
    )
    age_range: Optional[str] = Field(
        default=None,
        description="'elderly' | 'adult' | 'pediatric'",
    )
    kidney_function: Optional[str] = Field(
        default=None,
        description="e.g. 'eGFR < 30' | 'eGFR 30-60' | 'normal'",
    )

    @model_validator(mode="after")
    def derive_factors_from_structured_fields(self) -> "PatientProfile":
        """
        Auto-derive patient_factors from structured fields so the
        retrieval system always sees a complete factor list.
        """
        factors = set(self.patient_factors)

        # Pregnancy: if trimester is set, ensure 'pregnancy' in factors
        if self.pregnancy_trimester:
            factors.add("pregnancy")

        # Age derivation from date_of_birth
        if self.date_of_birth:
            try:
                dob = datetime.strptime(self.date_of_birth[:10], "%Y-%m-%d").date()
                today = date.today()
                age_years = (today - dob).days // 365
                if age_years >= 65:
                    factors.add("elderly")
                    if self.age_range is None:
                        object.__setattr__(self, "age_range", "elderly")
                elif age_years < 18:
                    factors.add("pediatric")
                    if self.age_range is None:
                        object.__setattr__(self, "age_range", "pediatric")
                elif self.age_range is None:
                    object.__setattr__(self, "age_range", "adult")
            except (ValueError, TypeError):
                pass

        # BMI / obesity derivation
        if self.height_cm and self.weight_kg and self.height_cm > 0:
            bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
            if bmi >= 30:
                factors.add("obesity")

        # Merge chronic_conditions into comorbidities for downstream use
        all_comorbidities = list(set(self.comorbidities) | set(self.chronic_conditions))
        object.__setattr__(self, "comorbidities", all_comorbidities)

        # Apply derived factors
        object.__setattr__(self, "patient_factors", sorted(factors))

        # Ensure target_drugs contains target_drug for single-drug compat
        if self.target_drug and self.target_drug not in self.target_drugs:
            object.__setattr__(self, "target_drugs", [self.target_drug] + list(self.target_drugs))
        elif self.target_drugs and not self.target_drug:
            object.__setattr__(self, "target_drug", self.target_drugs[0])

        return self


# ─── Clinical Context ──────────────────────────────────────────────────────────

class ClinicalContext(BaseModel):
    """Extracted clinical context from user query."""
    drugs: list[str] = Field(default_factory=list, description="Drug names mentioned")
    drug_ids: list[str] = Field(default_factory=list, description="Normalized drug IDs")
    diseases: list[str] = Field(default_factory=list, description="Disease/condition mentions")
    disease_areas: list[str] = Field(default_factory=list, description="Normalized disease areas")
    patient_factors: list[str] = Field(default_factory=list, description="Patient-specific factors")
    comorbidities: list[str] = Field(default_factory=list, description="Comorbid conditions")
    current_medications: list[str] = Field(default_factory=list, description="Other medications mentioned")
    allergies: list[str] = Field(default_factory=list, description="Allergies mentioned")
    clinical_intent: str = Field(default="", description="What the user wants to know")
    is_personalized: bool = Field(default=False, description="Is this a personalized medical request?")
    needs_drug_evidence: bool = Field(default=True, description="Does this need drug evidence?")
    confidence: float = Field(default=0.0, description="Extraction confidence 0-1")


# ─── Evidence ─────────────────────────────────────────────────────────────────

class EvidenceChunk(BaseModel):
    """A single retrieved piece of drug evidence."""
    chunk_id: str
    source_type: SourceType
    content: str
    score: float = 0.0

    # Drug metadata
    drug_name: Optional[str] = None
    drug_id: Optional[str] = None
    section_type: Optional[str] = None
    target_patient_factors: list[str] = Field(default_factory=list)
    category: Optional[str] = None
    has_boxed_warning: bool = False
    has_contraindications: bool = False
    primary_indication: Optional[str] = None

    def citation_str(self) -> str:
        """Format as a citation string using standardized [chunk_id] format."""
        return f"[{self.chunk_id}]"


# ─── Retrieval Plan ────────────────────────────────────────────────────────────

class RetrievalPlan(BaseModel):
    """Plan for what drug evidence to retrieve and how."""
    search_drug: bool = True
    drug_subqueries: list[str] = Field(default_factory=list)
    drug_filters: dict[str, Any] = Field(default_factory=dict)
    priority_drug_sections: list[str] = Field(default_factory=list)
    patient_factor_filters: list[str] = Field(
        default_factory=list,
        description="Patient factors to prioritize in retrieval",
    )


# ─── Risk Findings ────────────────────────────────────────────────────────────

class RiskFinding(BaseModel):
    """A single tiered risk finding for a specific patient factor."""
    patient_factor: str = Field(description="Which factor this finding addresses")
    tier: RiskTier
    summary: str = Field(default="", description="One-sentence clinical summary")
    rationale: str = Field(default="", description="Detailed reasoning from the KB")
    exact_quote: str = Field(default="", description="Direct quote from the source chunk")
    source_chunks: list[EvidenceChunk] = Field(default_factory=list)
    source_section_types: list[str] = Field(default_factory=list)
    is_deterministic: bool = Field(
        default=False,
        description="True if tier was set by rule-based pass (cannot be downgraded by LLM)",
    )

    def citation_str(self) -> str:
        return "; ".join(c.citation_str() for c in self.source_chunks[:2]) or "No documented source in KB"


# ─── Drug Overview ────────────────────────────────────────────────────────────

class DrugOverview(BaseModel):
    """Structured drug overview sourced from KB chunks."""
    drug_name: str
    drug_id: str
    drug_class: str = ""
    primary_indication: str = ""
    mechanism: str = ""
    source_chunks: list[EvidenceChunk] = Field(default_factory=list)


# ─── Claims & Grounding ────────────────────────────────────────────────────────

class Claim(BaseModel):
    """A single medical claim extracted from a draft response."""
    claim_id: str
    text: str
    claim_type: str = ""  # "recommendation", "warning", "fact", "comparison"


class GroundedClaim(BaseModel):
    """A claim with supporting evidence verified."""
    claim: Claim
    support_level: SupportLevel
    supporting_chunks: list[EvidenceChunk] = Field(default_factory=list)
    citation: str = ""
    note: str = ""


# ─── Safety ───────────────────────────────────────────────────────────────────

class SafetyAssessment(BaseModel):
    """Safety gate assessment result."""
    decision: SafetyDecision
    reasons: list[str] = Field(default_factory=list)
    modifications: list[str] = Field(default_factory=list)
    disclaimer_required: bool = True
    refusal_message: Optional[str] = None


# ─── Execution Trace ──────────────────────────────────────────────────────────

class ExecutionTrace(BaseModel):
    """Structured execution trace for observability."""
    query_category: str = ""
    interaction_mode: str = ""
    clinical_context: Optional[ClinicalContext] = None
    retrieval_plan: Optional[RetrievalPlan] = None
    drug_chunks_retrieved: int = 0
    drug_sources_used: list[str] = Field(default_factory=list)
    risk_findings_count: int = 0
    total_claims: int = 0
    grounded_claims: int = 0
    ungrounded_claims: int = 0
    safety_decision: str = ""
    processing_steps: list[str] = Field(default_factory=list)
    # Retrieval quality details
    chunks_filtered_by_threshold: int = 0
    reretrieval_attempted: bool = False
    grounding_type: str = ""  # P2-C: Document type of grounding performed


# ─── Final Response ────────────────────────────────────────────────────────────

class StructuredResponse(BaseModel):
    """The final structured response delivered to the user."""
    # Core
    query: str
    query_category: str
    interaction_mode: str = ""

    # Clinical context detected
    clinical_context_summary: str = ""
    detected_drugs: list[str] = Field(default_factory=list)
    detected_diseases: list[str] = Field(default_factory=list)
    detected_patient_factors: list[str] = Field(default_factory=list)

    # Drug evidence
    drug_evidence_summary: str = ""
    retrieved_evidence: list[EvidenceChunk] = Field(default_factory=list)

    # Risk report outputs
    risk_findings: list[RiskFinding] = Field(default_factory=list)
    drug_overview: Optional[DrugOverview] = None

    # Grounded response
    main_response: str = ""
    key_points: list[str] = Field(default_factory=list)
    key_warnings: list[str] = Field(default_factory=list)
    evidence_limitations: list[str] = Field(default_factory=list)

    # Citations
    citations: list[str] = Field(default_factory=list)
    grounded_claims: list[GroundedClaim] = Field(default_factory=list)

    # Metadata
    evidence_quality: str = ""  # high, medium, low
    safety_assessment: Optional[SafetyAssessment] = None
    disclaimer: str = ""
    execution_trace: Optional[ExecutionTrace] = None

    # Patient profile snapshot (for risk reports)
    patient_profile_summary: dict = Field(default_factory=dict)

    # Refusal
    is_refused: bool = False
    refusal_reason: str = ""
