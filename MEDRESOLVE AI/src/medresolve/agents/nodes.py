"""
MEDRESOLVE AI — LangGraph Nodes
All graph nodes implementing the drug-only personalized clinical pipeline.

Rebuild from plan — key changes:
- plan_retrieval: now DETERMINISTIC (no LLM call) — saves ~3s latency
- check_sufficiency: now DETERMINISTIC with actual re-retrieval on failure
- ground_claims: now DETERMINISTIC citation verification (no LLM self-check)
- safety_gate: LLM call removed — deterministic pattern checks only
- assess_risk: fixed SAFE vs NO_DATA, removed [:600] truncation, demote → NO_DATA not SAFE
- format_response: produces structured markdown with evidence table for both modes
- synthesize_response: passes patient_profile_summary to grounding prompt
"""

from __future__ import annotations
import json
import re
import uuid
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
import structlog

from medresolve.config import get_settings
from medresolve.models import (
    ClinicalContext, RetrievalPlan, EvidenceChunk, SourceType,
    GroundedClaim, Claim, SafetyAssessment, StructuredResponse,
    ExecutionTrace, QueryCategory, SafetyDecision, SupportLevel,
    PatientProfile, RiskFinding, RiskTier, DrugOverview, InteractionMode,
)
from medresolve.agents.state import MedResolveState
from medresolve.agents.prompts import (
    CLASSIFY_PROMPT, RISK_ASSESSMENT_PROMPT, SYNTHESIZE_PROMPT,
    CHAT_SYNTHESIZE_PROMPT, STANDARD_DISCLAIMER, OUT_OF_SCOPE_TEMPLATE,
    AMBIGUOUS_TEMPLATE, SAFETY_REFUSAL_TEMPLATE,
)
from medresolve.retrieval.hybrid_retriever import build_retriever
from medresolve.ingestion.drug_normalizer import _to_drug_id  # P1-RET-3: drug_id normalization

logger = structlog.get_logger(__name__)

_settings = get_settings()

# P1-INT-1: Module-level cached retriever — avoids recreating ChromaDB client on every
# retrieve_drug_evidence and verify_and_retrieve call (multiple times per request).
_retriever_cache: dict = {}

# ─── LLM Factory ──────────────────────────────────────────────────────────────

def get_llm(temperature: float | None = None) -> ChatGoogleGenerativeAI:
    """Get configured Gemini LLM instance."""
    return ChatGoogleGenerativeAI(
        model=_settings.gemini_model,
        temperature=temperature if temperature is not None else _settings.gemini_temperature,
        google_api_key=_settings.google_api_key,
        max_output_tokens=_settings.gemini_max_tokens,
    )


def _extract_content(content: str | list) -> str:
    """Normalise LLM result.content to a plain string.

    Gemini 3.x returns a list of content parts instead of a bare string.
    Each part may be:
      - a plain str
      - a dict like {'type': 'text', 'text': '...', 'extras': {...}}
      - an object with a .text attribute
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
            elif hasattr(part, "text"):
                parts.append(part.text)
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


def _safe_json_parse(raw: str | list) -> dict:
    """Safely parse JSON from LLM output, stripping markdown fences if needed."""
    raw = _extract_content(raw)
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {}


# ─── Deterministic Query Construction ─────────────────────────────────────────

def _build_retrieval_queries(
    query: str,
    context: ClinicalContext,
    patient_profile: PatientProfile | None,
    interaction_mode: str,
) -> tuple[list[str], list[str]]:
    """
    Build sub-queries and section priorities DETERMINISTICALLY.
    Replaces the LLM plan_retrieval call — saves ~3s latency.

    Returns:
        (sub_queries, priority_sections)
    """
    drugs = context.drugs or (
        [patient_profile.target_drug] if patient_profile and patient_profile.target_drug else []
    )
    all_factors = list(set(
        context.patient_factors
        + context.comorbidities
        + (patient_profile.patient_factors if patient_profile else [])
        + (patient_profile.comorbidities if patient_profile else [])
    ))

    sub_queries = []

    if interaction_mode == InteractionMode.RISK_REPORT.value:
        # Risk report: generate per-factor queries for targeted retrieval
        for drug in drugs[:_settings.max_retrieval_drugs]:
            # Main safety query
            sub_queries.append(f"{drug} contraindications warnings safety")
            # Per-factor queries
            for factor in all_factors[:_settings.max_retrieval_factors]:
                sub_queries.append(f"{drug} {factor.replace('_', ' ')} safety considerations")
            # Drug interactions
            meds = (patient_profile.current_medications if patient_profile else []) + context.current_medications
            if meds:
                sub_queries.append(f"{drug} drug interactions {' '.join(meds[:2])}")

        priority_sections = [
            "BOXED_WARNING", "CONTRAINDICATIONS", "WARNINGS_AND_PRECAUTIONS",
            "PREGNANCY", "RENAL_IMPAIRMENT", "HEPATIC_IMPAIRMENT",
            "GERIATRIC_USE", "PEDIATRIC_USE", "LACTATION",
            "DRUG_INTERACTIONS", "DOSAGE_AND_ADMINISTRATION", "DRUG_OVERVIEW",
        ]
    else:
        # Chat mode: use original query + drug-specific queries
        sub_queries.append(query)
        for drug in drugs[:_settings.max_retrieval_drugs]:
            sub_queries.append(f"{drug} {query}")
        if all_factors:
            sub_queries.append(f"{' '.join(drugs[:1])} {' '.join(all_factors[:2])}")

        priority_sections = [
            "CONTRAINDICATIONS", "WARNINGS_AND_PRECAUTIONS", "BOXED_WARNING",
            "DRUG_INTERACTIONS", "DOSAGE_AND_ADMINISTRATION", "DRUG_OVERVIEW",
            "PREGNANCY", "RENAL_IMPAIRMENT",
        ]

    # Deduplicate while preserving order
    seen = set()
    unique_queries = []
    for q in sub_queries:
        if q.lower() not in seen and q.strip():
            seen.add(q.lower())
            unique_queries.append(q)

    return unique_queries[:_settings.max_subqueries], priority_sections


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1: classify_and_extract
# ═══════════════════════════════════════════════════════════════════════════════

def classify_and_extract(state: MedResolveState) -> MedResolveState:
    """
    Node 1: Classify query and extract clinical context.
    Detects drugs, diseases, patient factors, interaction mode.
    LLM CALL 1/3 (only in chat mode; skipped for form-based risk reports).
    """
    query = state["query"]
    conversation_history = state.get("conversation_history", [])
    patient_profile = state.get("patient_profile")

    logger.info("node_classify_start", query=query[:100])

    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("classify_and_extract")

    # If a patient_profile was submitted (form-based), force risk_report mode — no LLM needed
    if patient_profile and patient_profile.target_drug:
        context = ClinicalContext(
            drugs=[patient_profile.target_drug],
            drug_ids=[patient_profile.target_drug_id] if patient_profile.target_drug_id else [],
            diseases=patient_profile.comorbidities,
            patient_factors=patient_profile.patient_factors,
            comorbidities=patient_profile.comorbidities,
            current_medications=patient_profile.current_medications,
            allergies=patient_profile.allergies,
            clinical_intent=f"Personalized risk assessment for {patient_profile.target_drug}",
            is_personalized=False,  # Form-based is explicitly allowed
            needs_drug_evidence=True,
            confidence=1.0,
        )
        interaction_mode = InteractionMode.RISK_REPORT.value
        query_category = QueryCategory.RISK_REPORT.value
        trace.query_category = query_category
        trace.interaction_mode = interaction_mode
        trace.clinical_context = context
        return {
            **state,
            "clinical_context": context,
            "query_category": query_category,
            "interaction_mode": interaction_mode,
            "execution_trace": trace,
            "error_message": "",
        }

    # Conversational path: use LLM to classify (LLM CALL 1)
    conversation_context = ""
    if conversation_history:
        recent = conversation_history[-4:]  # Last 2 turns
        conversation_context = "\n".join(
            f"{m.get('role', 'user').title()}: {m.get('content', '')[:200]}"
            for m in recent
        )

    try:
        llm = get_llm()
        chain = CLASSIFY_PROMPT | llm

        result = chain.invoke({
            "query": query,
            "conversation_context": conversation_context or "No prior context",
        })
        parsed = _safe_json_parse(_extract_content(result.content))

        if not parsed:
            raise ValueError("Empty classification result")

        context = ClinicalContext(
            drugs=parsed.get("drugs", []),
            drug_ids=parsed.get("drug_ids", []),
            diseases=parsed.get("diseases", []),
            disease_areas=parsed.get("disease_areas", []),
            patient_factors=parsed.get("patient_factors", []),
            comorbidities=parsed.get("comorbidities", []),
            current_medications=parsed.get("current_medications", []),
            allergies=parsed.get("allergies", []),
            clinical_intent=parsed.get("clinical_intent", ""),
            is_personalized=parsed.get("is_personalized", False),
            needs_drug_evidence=parsed.get("needs_drug_evidence", True),
            confidence=parsed.get("confidence", 0.7),
        )

        query_category = parsed.get("query_category", QueryCategory.DRUG_ONLY)
        interaction_mode = parsed.get("interaction_mode", InteractionMode.CHAT_QUERY.value)

        trace.query_category = query_category
        trace.interaction_mode = interaction_mode
        trace.clinical_context = context

        logger.info(
            "classification_complete",
            category=query_category,
            mode=interaction_mode,
            drugs=context.drugs,
            diseases=context.diseases,
        )

        return {
            **state,
            "clinical_context": context,
            "query_category": query_category,
            "interaction_mode": interaction_mode,
            "execution_trace": trace,
            "error_message": "",
        }

    except Exception as e:
        logger.error("classification_failed", error=str(e))
        return {
            **state,
            "query_category": QueryCategory.DRUG_ONLY.value,
            "interaction_mode": InteractionMode.CHAT_QUERY.value,
            "clinical_context": ClinicalContext(),
            "execution_trace": trace,
            "error_message": f"Classification error: {e}",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2: retrieve_drug_evidence
# (Previously nodes 2+3: plan_retrieval + retrieve_drug_evidence merged)
# No LLM call — deterministic query construction + hybrid retrieval
# ═══════════════════════════════════════════════════════════════════════════════

def retrieve_drug_evidence(state: MedResolveState) -> MedResolveState:
    """
    Node 2: Build retrieval plan deterministically, then execute hybrid retrieval.

    Replaces the old LLM-based plan_retrieval + retrieve_drug_evidence pair.
    No LLM call — saves ~3s latency with zero quality loss.
    """
    query = state["query"]
    context = state.get("clinical_context") or ClinicalContext()
    patient_profile = state.get("patient_profile")
    interaction_mode = state.get("interaction_mode", InteractionMode.CHAT_QUERY.value)
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("retrieve_drug_evidence")

    # Build queries and priorities deterministically
    sub_queries, priority_sections = _build_retrieval_queries(
        query, context, patient_profile, interaction_mode
    )

    # Build drug filter
    drug_ids = context.drug_ids[:]
    if patient_profile and patient_profile.target_drug_id:
        if patient_profile.target_drug_id not in drug_ids:
            drug_ids.insert(0, patient_profile.target_drug_id)

    # Store plan in trace
    plan = RetrievalPlan(
        search_drug=True,
        drug_subqueries=sub_queries,
        drug_filters={"drug_id": {"$eq": drug_ids[0]}} if drug_ids else {},
        priority_drug_sections=priority_sections,
        patient_factor_filters=list(set(
            context.patient_factors + context.comorbidities
            + (patient_profile.patient_factors if patient_profile else [])
        )),
    )
    trace.retrieval_plan = plan

    try:
        # P1-INT-1: Use cached retriever to avoid repeated ChromaDB client creation
        if "drugs" not in _retriever_cache:
            _retriever_cache["drugs"] = build_retriever("drugs")
        retriever = _retriever_cache["drugs"]
        all_chunks: list[EvidenceChunk] = []
        seen_ids: set[str] = set()

        # P1-RET-3: Normalize all drug_ids to snake_case so metadata filter matches index
        drug_ids = [_to_drug_id(d) for d in drug_ids if d]
        target_drug_ids = drug_ids[:_settings.max_retrieval_drugs] if drug_ids else [None]

        for drug_id in target_drug_ids:
            drug_filter = {"drug_id": {"$eq": drug_id}} if drug_id else None

            # Run each sub-query with drug filter
            for subquery in sub_queries[:_settings.max_subqueries_per_drug]:
                try:
                    chunks = retriever.retrieve(
                        query=subquery,
                        k=_settings.retrieval_drug_k,
                        metadata_filter=drug_filter,
                        # P2-RET-5: use config values instead of hardcoded 12
                        dense_k=_settings.retrieval_dense_k,
                        bm25_k=_settings.retrieval_bm25_k,
                    )
                    for chunk in chunks:
                        if chunk.chunk_id not in seen_ids:
                            all_chunks.append(chunk)
                            seen_ids.add(chunk.chunk_id)
                except Exception as e:
                    logger.warning("subquery_retrieval_failed", query=subquery[:60], error=str(e))

            # In risk_report mode: always fetch critical safety sections directly
            if interaction_mode == InteractionMode.RISK_REPORT.value and drug_id:
                critical_sections = [
                    "BOXED_WARNING", "CONTRAINDICATIONS", "WARNINGS_AND_PRECAUTIONS",
                    "DRUG_INTERACTIONS",
                ]
                # Add patient-factor-specific sections
                all_factors = list(set(
                    context.patient_factors + context.comorbidities
                    + (patient_profile.patient_factors if patient_profile else [])
                    + (patient_profile.comorbidities if patient_profile else [])
                ))
                factor_section_map = {
                    "pregnancy": "PREGNANCY",
                    "renal_impairment": "RENAL_IMPAIRMENT",
                    "hepatic_impairment": "HEPATIC_IMPAIRMENT",
                    "elderly": "GERIATRIC_USE",
                    "pediatric": "PEDIATRIC_USE",
                    "lactation": "LACTATION",
                }
                for factor in all_factors:
                    factor_clean = factor.lower().replace(" ", "_").replace("/", "_")
                    if factor_clean in factor_section_map:
                        critical_sections.append(factor_section_map[factor_clean])
                    # Fuzzy match
                    for key, section in factor_section_map.items():
                        if key in factor_clean and section not in critical_sections:
                            critical_sections.append(section)

                for section in list(set(critical_sections)):
                    section_filter = {
                        "$and": [
                            {"drug_id": {"$eq": drug_id}},
                            {"section_type": {"$eq": section}},
                        ]
                    }
                    try:
                        sec_query = f"{context.drugs[0] if context.drugs else drug_id} {section.lower().replace('_', ' ')}"
                        sec_chunks = retriever.retrieve(
                            query=sec_query,
                            k=2,
                            metadata_filter=section_filter,
                            dense_k=8,
                            bm25_k=8,
                        )
                        for chunk in sec_chunks:
                            if chunk.chunk_id not in seen_ids:
                                all_chunks.append(chunk)
                                seen_ids.add(chunk.chunk_id)
                    except Exception:
                        pass  # Section may not exist — continue

        # Fallback: no drug-id filter
        if not all_chunks and sub_queries:
            for subquery in sub_queries[:2]:
                try:
                    chunks = retriever.retrieve(
                        query=subquery,
                        k=_settings.retrieval_drug_k,
                        dense_k=_settings.retrieval_dense_k,
                        bm25_k=_settings.retrieval_bm25_k,
                    )
                    for chunk in chunks:
                        # P1-C post-filter: discard wrong drugs if target is known
                        if target_drug_ids and target_drug_ids != [None]:
                            if chunk.drug_id not in target_drug_ids:
                                logger.warning("fallback_discarded_wrong_drug", expected=target_drug_ids, found=chunk.drug_id)
                                continue
                        if chunk.chunk_id not in seen_ids:
                            all_chunks.append(chunk)
                            seen_ids.add(chunk.chunk_id)
                except Exception as e:
                    logger.error("fallback_retrieval_failed", error=str(e))

        # P1-B: Global relevance sort before returning
        all_chunks.sort(key=lambda c: c.score, reverse=True)

        trace.drug_chunks_retrieved = len(all_chunks)
        trace.drug_sources_used = list({c.drug_name for c in all_chunks if c.drug_name})

        logger.info(
            "drug_evidence_retrieved",
            count=len(all_chunks),
            drugs=trace.drug_sources_used,
            sections=list({c.section_type for c in all_chunks}),
        )

        return {**state, "drug_evidence": all_chunks, "retrieval_plan": plan, "execution_trace": trace}

    except Exception as e:
        logger.error("drug_retrieval_failed", error=str(e))
        return {
            **state, "drug_evidence": [], "retrieval_plan": plan, "execution_trace": trace,
            "error_message": f"Drug retrieval error: {e}",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3: verify_and_retrieve
# (Replaces old check_sufficiency — actually re-retrieves if insufficient)
# No LLM call — deterministic threshold check
# ═══════════════════════════════════════════════════════════════════════════════

def verify_and_retrieve(state: MedResolveState) -> MedResolveState:
    """
    Node 3: Verify retrieved evidence is sufficient; re-retrieve if not.

    Uses deterministic quality checks instead of LLM sufficiency check.
    Actually executes re-retrieval (unlike old check_sufficiency which parsed
    additional_queries but never used them).
    """
    drug_evidence = state.get("drug_evidence", [])
    check_count = state.get("sufficiency_check_count", 0)
    interaction_mode = state.get("interaction_mode", InteractionMode.CHAT_QUERY.value)
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("verify_and_retrieve")

    min_chunks = (
        _settings.retrieval_min_chunks_risk
        if interaction_mode == InteractionMode.RISK_REPORT.value
        else _settings.retrieval_min_chunks_chat
    )

    total = len(drug_evidence)
    sufficient = total >= min_chunks

    # Additional check for risk_report: need at least one safety-relevant chunk
    if sufficient and interaction_mode == InteractionMode.RISK_REPORT.value:
        safety_sections = {"BOXED_WARNING", "CONTRAINDICATIONS", "WARNINGS_AND_PRECAUTIONS",
                           "PREGNANCY", "RENAL_IMPAIRMENT", "HEPATIC_IMPAIRMENT"}
        has_safety = any(c.section_type in safety_sections for c in drug_evidence)
        if not has_safety:
            sufficient = False
            logger.info("verify_insufficient", reason="no_safety_sections", total=total)

    if not sufficient and check_count < _settings.max_reretrieval_attempts:
        logger.info("verify_reretrieval_triggered", count=total, min_required=min_chunks)
        trace.reretrieval_attempted = True

        # Actually execute re-retrieval with broader queries
        context = state.get("clinical_context") or ClinicalContext()
        patient_profile = state.get("patient_profile")

        try:
            # P1-INT-1: reuse cached retriever — avoids recreating ChromaDB client
            if "drugs" not in _retriever_cache:
                _retriever_cache["drugs"] = build_retriever("drugs")
            retriever = _retriever_cache["drugs"]
            existing_ids = {c.chunk_id for c in drug_evidence}
            extra_chunks: list[EvidenceChunk] = []

            # Try broader queries without drug_id filter
            fallback_queries = []
            target_drugs = []
            if context.drugs:
                fallback_queries.append(f"{context.drugs[0]} safety warnings contraindications")
                fallback_queries.append(f"{context.drugs[0]} patient populations")
                target_drugs.extend(context.drug_ids)
            if patient_profile and patient_profile.target_drug:
                fallback_queries.append(
                    f"{patient_profile.target_drug} safety warnings contraindications"
                )
                if patient_profile.target_drug_id:
                    target_drugs.append(patient_profile.target_drug_id)

            # P1-C: Use metadata_filter if we know the target drugs
            target_drugs = list(set(d for d in target_drugs if d))
            metadata_filter = {"drug_id": {"$in": target_drugs}} if target_drugs else None

            for q in fallback_queries[:3]:
                try:
                    chunks = retriever.retrieve(
                        query=q,
                        k=5,
                        dense_k=_settings.retrieval_dense_k,
                        bm25_k=_settings.retrieval_bm25_k,
                        metadata_filter=metadata_filter
                    )
                    for chunk in chunks:
                        if chunk.chunk_id not in existing_ids:
                            extra_chunks.append(chunk)
                            existing_ids.add(chunk.chunk_id)
                except Exception:
                    pass

            if extra_chunks:
                drug_evidence = drug_evidence + extra_chunks
                trace.drug_chunks_retrieved = len(drug_evidence)
                logger.info("reretrieval_success", added=len(extra_chunks), total=len(drug_evidence))
                sufficient = len(drug_evidence) >= min_chunks

        except Exception as e:
            logger.error("reretrieval_failed", error=str(e))

    logger.info("evidence_sufficiency", sufficient=sufficient, total=len(drug_evidence))

    return {
        **state,
        "drug_evidence": drug_evidence,
        "evidence_sufficient": sufficient,  # P2-B: Propagate actual sufficiency
        "sufficiency_check_count": check_count + 1,
        "execution_trace": trace,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 4: assess_risk
# (Risk Report mode only — LLM CALL 2/3 for risk_report mode)
# ═══════════════════════════════════════════════════════════════════════════════

def assess_risk(state: MedResolveState) -> MedResolveState:
    """
    Node 4: Hybrid risk assessment — deterministic metadata scan +
    LLM structured grading with mandatory chunk citation + grounding validation.
    Also extracts Drug Overview from retrieved chunks.
    Only activated in risk_report interaction mode.

    Key fixes:
    - Invalid chunk citations → NO_DATA (not SAFE) — silence is not safety
    - Full chunk content shown to LLM (no [:600] truncation)
    - exact_quote extracted from findings
    """
    drug_evidence = state.get("drug_evidence", [])
    patient_profile = state.get("patient_profile")
    context = state.get("clinical_context") or ClinicalContext()
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("assess_risk")

    if not drug_evidence:
        logger.warning("assess_risk_no_evidence")
        return {**state, "risk_findings": [], "drug_overview": None, "execution_trace": trace}

    # Build patient factors list
    all_factors = list(set(
        (patient_profile.comorbidities if patient_profile else [])
        + (patient_profile.patient_factors if patient_profile else [])
        + context.patient_factors
        + context.comorbidities
    ))
    target_drug = (patient_profile.target_drug if patient_profile else None) or (
        context.drugs[0] if context.drugs else "Unknown"
    )

    # ── Step 1: Deterministic metadata scan ───────────────────────────────────
    deterministic_flags: list[dict] = []
    chunk_lookup = {c.chunk_id: c for c in drug_evidence}

    for chunk in drug_evidence:
        if chunk.has_boxed_warning and chunk.section_type == "BOXED_WARNING":
            deterministic_flags.append({
                "chunk_id": chunk.chunk_id,
                "tier": "HIGH_WARNING",
                "reason": "has_boxed_warning flag is True in BOXED_WARNING section",
                "patient_factor": "general",
            })
        if chunk.has_contraindications and chunk.section_type == "CONTRAINDICATIONS":
            # Check if any patient factor is in target_patient_factors
            overlapping = [f for f in all_factors if any(
                f.lower() in tpf.lower() or tpf.lower() in f.lower()
                for tpf in chunk.target_patient_factors
            )]
            if overlapping or not all_factors:
                deterministic_flags.append({
                    "chunk_id": chunk.chunk_id,
                    "tier": "HIGH_WARNING",
                    "reason": "has_contraindications in CONTRAINDICATIONS section",
                    "patient_factor": overlapping[0] if overlapping else "general",
                })

    # ── Step 2: LLM structured grading (LLM CALL 2) ───────────────────────────
    # Show FULL chunk content to LLM (no truncation)
    evidence_text = "\n\n---\n\n".join(
        f"[ID: {c.chunk_id} | {c.drug_name} | Section: {c.section_type or 'General'} | "
        f"BoxedWarning:{c.has_boxed_warning} | Contraindication:{c.has_contraindications}]\n"
        f"TargetFactors: {', '.join(c.target_patient_factors) or 'None'}\n"
        f"Score: {round(c.score, 3)}\n\n"
        f"{c.content}"  # Full content — no truncation
        for c in drug_evidence[:15]
    )

    age_kidney = " | ".join(filter(None, [
        patient_profile.age_range if patient_profile else "",
        patient_profile.kidney_function if patient_profile else "",
    ])) or "Not specified"

    llm_findings: list[dict] = []
    llm_overview: dict = {}

    try:
        llm = get_llm(temperature=0.1)
        chain = RISK_ASSESSMENT_PROMPT | llm

        result = chain.invoke({
            "target_drug": target_drug,
            "comorbidities": json.dumps(all_factors),
            "patient_factors": json.dumps(context.patient_factors),
            "current_medications": json.dumps(
                (patient_profile.current_medications if patient_profile else [])
                + context.current_medications
            ),
            "allergies": json.dumps(
                (patient_profile.allergies if patient_profile else []) + context.allergies
            ),
            "age_kidney": age_kidney,
            "evidence_chunks": evidence_text,
            "deterministic_flags": json.dumps(deterministic_flags),
        })
        parsed = _safe_json_parse(_extract_content(result.content))
        llm_findings = parsed.get("risk_findings", [])
        llm_overview = parsed.get("drug_overview", {})

    except Exception as e:
        logger.error("risk_assessment_llm_failed", error=str(e))

    # ── Step 3: Grounding validation + build RiskFinding objects ──────────────
    deterministic_high_ids = {f["chunk_id"] for f in deterministic_flags if f["tier"] == "HIGH_WARNING"}

    risk_findings: list[RiskFinding] = []

    if llm_findings:
        for finding_data in llm_findings:
            tier_str = finding_data.get("tier", "NO_DATA")
            cited_ids = finding_data.get("chunk_ids", [])
            patient_factor = finding_data.get("patient_factor", "general")

            # Grounding validation: verify chunk IDs exist in retrieved set
            valid_chunks = [chunk_lookup[cid] for cid in cited_ids if cid in chunk_lookup]

            # KEY FIX: If HIGH/MODERATE cited invalid chunk_id → NO_DATA, NOT SAFE
            # "No valid citation" ≠ "safe" — it means we can't verify the warning
            if tier_str in ("HIGH_WARNING", "MODERATE_CAUTION") and not valid_chunks:
                tier_str = "NO_DATA"
                finding_data["rationale"] = (
                    "Warning could not be verified against knowledge base "
                    "(cited chunk_id not found in retrieved evidence) — "
                    "consult the full drug label directly."
                )
                finding_data["summary"] = "Unverified — consult drug label"
                finding_data["exact_quote"] = ""

            # Cannot downgrade deterministic HIGH_WARNINGs
            is_deterministic = any(cid in deterministic_high_ids for cid in cited_ids)
            if is_deterministic and tier_str != "HIGH_WARNING":
                tier_str = "HIGH_WARNING"  # Restore — cannot be downgraded

            try:
                tier = RiskTier(tier_str.lower())
            except ValueError:
                tier = RiskTier.NO_DATA

            risk_findings.append(RiskFinding(
                patient_factor=patient_factor,
                tier=tier,
                summary=finding_data.get("summary", ""),
                rationale=finding_data.get("rationale", ""),
                exact_quote=finding_data.get("exact_quote", ""),
                source_chunks=valid_chunks,
                source_section_types=finding_data.get("section_types", []),
                is_deterministic=is_deterministic,
            ))
    else:
        # Fallback: create findings from deterministic flags only
        for flag in deterministic_flags:
            cid = flag["chunk_id"]
            chunk = chunk_lookup.get(cid)
            risk_findings.append(RiskFinding(
                patient_factor=flag["patient_factor"],
                tier=RiskTier.HIGH_WARNING,
                summary=f"Boxed warning or contraindication detected in {target_drug}",
                rationale=flag["reason"],
                exact_quote="",
                source_chunks=[chunk] if chunk else [],
                source_section_types=["CONTRAINDICATIONS"],
                is_deterministic=True,
            ))

    # If still no findings and we have patient factors, add NO_DATA findings (not SAFE)
    if not risk_findings and all_factors:
        for factor in all_factors[:5]:
            risk_findings.append(RiskFinding(
                patient_factor=factor,
                tier=RiskTier.NO_DATA,
                summary=f"No documented information found in knowledge base for {factor}",
                rationale="No relevant chunk retrieved addressing this patient factor. Consult the full drug label.",
                exact_quote="",
                source_chunks=[],
                source_section_types=[],
                is_deterministic=False,
            ))

    # ── Build DrugOverview ─────────────────────────────────────────────────────
    drug_overview = None
    if llm_overview:
        overview_chunk_ids = llm_overview.get("overview_chunk_ids", [])
        overview_chunks = [chunk_lookup[cid] for cid in overview_chunk_ids if cid in chunk_lookup]
        # Fallback: look for DRUG_OVERVIEW section chunk
        if not overview_chunks:
            overview_chunks = [c for c in drug_evidence if c.section_type == "DRUG_OVERVIEW"][:2]
        drug_overview = DrugOverview(
            drug_name=target_drug,
            drug_id=(patient_profile.target_drug_id if patient_profile else "") or (
                context.drug_ids[0] if context.drug_ids else ""
            ),
            drug_class=llm_overview.get("drug_class", ""),
            primary_indication=llm_overview.get("primary_indication", ""),
            mechanism=llm_overview.get("mechanism", ""),
            source_chunks=overview_chunks,
        )

    trace.risk_findings_count = len(risk_findings)
    logger.info(
        "risk_assessment_complete",
        drug=target_drug,
        findings=len(risk_findings),
        high=sum(1 for f in risk_findings if f.tier == RiskTier.HIGH_WARNING),
        moderate=sum(1 for f in risk_findings if f.tier == RiskTier.MODERATE_CAUTION),
        safe=sum(1 for f in risk_findings if f.tier == RiskTier.SAFE),
        no_data=sum(1 for f in risk_findings if f.tier == RiskTier.NO_DATA),
    )

    return {
        **state,
        "risk_findings": risk_findings,
        "drug_overview": drug_overview,
        "execution_trace": trace,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 5: synthesize_response
# (LLM CALL 2/3 for chat, 3/3 for risk_report)
# ═══════════════════════════════════════════════════════════════════════════════

def synthesize_response(state: MedResolveState) -> MedResolveState:
    """
    Node 5: Generate the draft evidence-grounded response using hard grounding rules.

    The SYNTHESIZE_PROMPT now mandates [chunk_id] citations and prohibits
    use of general medical knowledge.
    """
    query = state["query"]
    context = state.get("clinical_context") or ClinicalContext()
    drug_evidence = state.get("drug_evidence", [])
    risk_findings = state.get("risk_findings", [])
    drug_overview = state.get("drug_overview")
    interaction_mode = state.get("interaction_mode", InteractionMode.CHAT_QUERY.value)
    conversation_history = state.get("conversation_history", [])
    patient_profile = state.get("patient_profile")
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("synthesize_response")

    # Format drug evidence — with chunk_id clearly labeled for citation
    dr_text = "\n\n---\n\n".join(
        f"[chunk_id: {c.chunk_id} | Drug: {c.drug_name or 'Unknown'} | Section: {c.section_type or 'General'} | Score: {round(c.score, 3)}]\n{c.content}"
        for c in drug_evidence[:10]
    ) or "No drug evidence retrieved."

    # P2-B fix: Add a warning to the LLM if evidence is insufficient
    if not state.get("evidence_sufficient", True):
        dr_text = "**WARNING: System failed to retrieve sufficient evidence for this query. Be highly conservative and note the lack of evidence in your response.**\n\n" + dr_text

    # Format risk findings summary
    risk_findings_summary = ""
    if risk_findings:
        tier_icons = {
            RiskTier.HIGH_WARNING: "🔴",
            RiskTier.MODERATE_CAUTION: "🟠",
            RiskTier.SAFE: "🟢",
            RiskTier.NO_DATA: "⚪",
        }
        lines = []
        for f in risk_findings:
            icon = tier_icons.get(f.tier, "⚪")
            tier_label = f.tier.value.replace("_", " ").title()
            lines.append(f"{icon} {tier_label} — {f.patient_factor}: {f.summary}")
            if f.exact_quote:
                lines.append(f'   ↳ Quote: "{f.exact_quote}"')
            if f.source_chunks:
                lines.append(f"   ↳ Citation: {f.citation_str()}")
        risk_findings_summary = "\n".join(lines)

    drug_overview_summary = ""
    if drug_overview:
        drug_overview_summary = (
            f"Drug: {drug_overview.drug_name}\n"
            f"Class: {drug_overview.drug_class}\n"
            f"Indication: {drug_overview.primary_indication}\n"
            f"Mechanism: {drug_overview.mechanism}"
        )

    # Format conversation history for chat mode
    conv_history_text = ""
    if conversation_history and interaction_mode == InteractionMode.CHAT_QUERY.value:
        conv_history_text = "\n".join(
            f"{m.get('role', 'user').title()}: {m.get('content', '')[:400]}"
            for m in conversation_history[-6:]
        )

    # Patient profile summary for context
    patient_summary = ""
    drug_name_for_prompt = ""
    if patient_profile:
        drug_name_for_prompt = patient_profile.target_drug
        parts = []
        if patient_profile.full_name:
            parts.append(f"Name: {patient_profile.full_name}")
        if patient_profile.age_range:
            parts.append(f"Age group: {patient_profile.age_range}")
        if patient_profile.gender:
            parts.append(f"Gender: {patient_profile.gender}")
        if patient_profile.patient_factors:
            parts.append(f"Patient factors: {', '.join(patient_profile.patient_factors)}")
        if patient_profile.comorbidities:
            parts.append(f"Comorbidities: {', '.join(patient_profile.comorbidities)}")
        if patient_profile.current_medications:
            parts.append(f"Current medications: {', '.join(patient_profile.current_medications)}")
        if patient_profile.kidney_function:
            parts.append(f"Kidney function: {patient_profile.kidney_function}")
        if patient_profile.pregnancy_trimester:
            parts.append(f"Pregnancy trimester: {patient_profile.pregnancy_trimester}")
        patient_summary = "\n".join(parts)
    else:
        drug_name_for_prompt = context.drugs[0] if context.drugs else "Unknown Drug"

    try:
        llm = get_llm(temperature=0.2)
        
        if interaction_mode == InteractionMode.CHAT_QUERY.value:
            chain = CHAT_SYNTHESIZE_PROMPT | llm
            result = chain.invoke({
                "query": query,
                "interaction_mode": interaction_mode,
                "drugs": json.dumps(context.drugs),
                "patient_factors": json.dumps(context.patient_factors),
                "conversation_history": conv_history_text or "No prior conversation",
                "drug_evidence": dr_text,
            })
        else:
            chain = SYNTHESIZE_PROMPT | llm
            result = chain.invoke({
                "query": query,
                "query_category": state.get("query_category", ""),
                "interaction_mode": interaction_mode,
                "drugs": json.dumps(context.drugs),
                "diseases": json.dumps(context.diseases),
                "patient_factors": json.dumps(context.patient_factors),
                "patient_profile_summary": patient_summary or "No patient profile submitted",
                "drug_name": drug_name_for_prompt,
                "conversation_history": conv_history_text or "No prior conversation",
                "drug_evidence": dr_text,
                "risk_findings_summary": risk_findings_summary or "Not applicable",
                "drug_overview_summary": drug_overview_summary or "Not applicable",
            })

        draft = _extract_content(result.content)
        logger.info("draft_synthesized", length=len(draft))

        return {**state, "draft_response": draft, "execution_trace": trace}

    except Exception as e:
        logger.error("synthesis_failed", error=str(e))
        fallback = f"Evidence synthesis encountered an error: {e}\n\nAvailable evidence:\n{dr_text[:500]}"
        return {**state, "draft_response": fallback, "execution_trace": trace}


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 6: ground_and_format
# (Merges old: ground_claims + safety_gate + format_response)
# No LLM calls — fully deterministic
# ═══════════════════════════════════════════════════════════════════════════════

def ground_and_format(state: MedResolveState) -> MedResolveState:
    """
    Node 6: Deterministic citation verification + safety gate + response formatting.

    Replaces 3 old nodes (ground_claims LLM, safety_gate LLM, format_response):
    1. DETERMINISTIC grounding: extract [chunk_id] citations from draft, verify they exist
    2. DETERMINISTIC safety: pattern-match for unsafe language (no LLM)
    3. Structured formatting: build evidence table + structured markdown output
    """
    query = state["query"]
    context = state.get("clinical_context") or ClinicalContext()
    draft = state.get("draft_response", "")
    risk_findings = state.get("risk_findings", [])
    drug_overview = state.get("drug_overview")
    drug_evidence = state.get("drug_evidence", [])
    interaction_mode = state.get("interaction_mode", "")
    patient_profile = state.get("patient_profile")
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("ground_and_format")

    chunk_lookup = {c.chunk_id: c for c in drug_evidence}

    # ── Step 1: Deterministic citation verification ────────────────────────────
    # Extract all [chunk_id] references from draft
    cited_ids = re.findall(r"\[([a-z][a-z0-9_]+)\]", draft)
    grounded: list[GroundedClaim] = []

    valid_citations = 0
    invalid_citations = []
    uncited_claim_count = 0

    for cid in set(cited_ids):
        if cid in chunk_lookup:
            valid_citations += 1
            chunk = chunk_lookup[cid]
            grounded.append(GroundedClaim(
                claim=Claim(claim_id=cid, text=f"Citation to {cid}", claim_type="citation"),
                support_level=SupportLevel.FULLY_SUPPORTED,
                supporting_chunks=[chunk],
                citation=chunk.citation_str(),
                note="Valid chunk_id found in retrieved evidence",
            ))
        else:
            invalid_citations.append(cid)
            grounded.append(GroundedClaim(
                claim=Claim(claim_id=cid, text=f"Invalid citation to {cid}", claim_type="citation"),
                support_level=SupportLevel.UNSUPPORTED,
                supporting_chunks=[],
                citation="",
                note=f"chunk_id '{cid}' not found in retrieved evidence — possible hallucination",
            ))

    # Flag any invalid citations in draft
    if invalid_citations:
        logger.warning(
            "invalid_citations_in_draft",
            invalid=invalid_citations,
            valid=valid_citations,
        )
        # Remove invalid citations from draft
        for bad_id in invalid_citations:
            draft = draft.replace(f"[{bad_id}]", f"[UNVERIFIED:{bad_id}]")

    trace.total_claims = len(cited_ids)
    trace.grounded_claims = valid_citations
    trace.ungrounded_claims = len(invalid_citations)

    # ── Step 2: Deterministic safety gate ────────────────────────────────────
    unsafe_patterns = [
        ("take x mg of", "individualized dosing"),
        ("you should take", "prescribing advice"),
        ("your diagnosis is", "diagnosis"),
        ("i diagnose", "diagnosis"),
        ("prescribe you", "prescribing"),
        ("i recommend you take", "prescribing advice"),
        ("your dose should be", "individualized dosing"),
    ]

    issues = []
    decision = SafetyDecision.SAFE
    draft_lower = draft.lower()
    for pattern, issue_type in unsafe_patterns:
        if pattern in draft_lower:
            issues.append(f"Contains {issue_type} language")
            decision = SafetyDecision.MODIFIED

    if context.is_personalized:
        decision = SafetyDecision.REFUSED
        issues.append("Personalized medical advice requested")

    trace.safety_decision = decision.value

    safety = SafetyAssessment(
        decision=decision,
        reasons=issues,
        disclaimer_required=True,
        refusal_message=SAFETY_REFUSAL_TEMPLATE.format(
            request_type="personalized prescribing advice"
        ) if decision == SafetyDecision.REFUSED else None,
    )

    # ── Handle refused requests ────────────────────────────────────────────────
    if decision == SafetyDecision.REFUSED:
        response = StructuredResponse(
            query=query,
            query_category=state.get("query_category", ""),
            interaction_mode=interaction_mode,
            is_refused=True,
            refusal_reason=safety.refusal_message or "Request not within scope",
            main_response=safety.refusal_message or "This request cannot be processed.",
            disclaimer=STANDARD_DISCLAIMER,
            safety_assessment=safety,
            execution_trace=trace,
        )
        return {**state, "final_response": response, "safety_assessment": safety,
                "grounded_claims": grounded, "execution_trace": trace}

    # ── Step 3: Build evidence table ──────────────────────────────────────────
    evidence_table_rows = []
    if interaction_mode != InteractionMode.CHAT_QUERY.value:
        for i, chunk in enumerate(drug_evidence[:12], 1):
            score_pct = f"{round(chunk.score, 3):.3f}"
            section = (chunk.section_type or "General").replace("_", " ").title()
            evidence_table_rows.append(
                f"| {i} | `{chunk.chunk_id}` | {chunk.drug_name or 'N/A'} | {section} | {score_pct} |"
            )

    evidence_table = ""
    if evidence_table_rows:
        evidence_table = (
            "\n## 📋 Evidence Used\n"
            "| # | Chunk ID | Drug | Section | Score |\n"
            "|---|----------|------|---------|-------|\n"
            + "\n".join(evidence_table_rows)
        )

    # ── Step 4: Append evidence table to draft if not already present ─────────
    if evidence_table and "## 📋 Evidence Used" not in draft:
        draft = draft.rstrip() + "\n\n" + evidence_table

    # ── Step 5: Collect citations and build response ──────────────────────────
    citations = [f"[{c.chunk_id}]" for c in drug_evidence[:15]]

    key_warnings = [
        f"[{f.tier.value.replace('_', ' ').title()}] {f.patient_factor}: {f.summary}"
        for f in risk_findings
        if f.tier == RiskTier.HIGH_WARNING
    ]
    key_points = [
        f"{f.patient_factor}: {f.summary}"
        for f in risk_findings
        if f.tier == RiskTier.MODERATE_CAUTION
    ]

    # Evidence quality
    total_evidence = len(drug_evidence)
    if total_evidence >= 8 and valid_citations >= 3:
        evidence_quality = "high"
    elif total_evidence >= 3:
        evidence_quality = "moderate"
    else:
        evidence_quality = "low"

    # Clinical context summary
    ctx_parts = []
    if context.drugs:
        ctx_parts.append(f"Drug(s): {', '.join(context.drugs)}")
    if context.diseases:
        ctx_parts.append(f"Condition(s): {', '.join(context.diseases)}")
    if context.patient_factors:
        ctx_parts.append(f"Patient factors: {', '.join(context.patient_factors)}")

    # Evidence limitations
    limitations = []
    
    # P2-C fix: Document the architectural limitation of chunk-existence grounding
    limitations.append("Grounding verifies chunk ID existence only; it does not semantically verify that the chunk supports the claim.")
    trace.grounding_type = "chunk_existence_only"
    if invalid_citations:
        limitations.append(
            f"{len(invalid_citations)} citation(s) in response could not be verified "
            f"against retrieved evidence: {', '.join(invalid_citations[:3])}"
        )
    no_data_findings = [f for f in risk_findings if f.tier == RiskTier.NO_DATA]
    if no_data_findings:
        factors = ", ".join(f.patient_factor for f in no_data_findings)
        limitations.append(f"No KB data found for patient factors: {factors} — consult drug label directly")
    if total_evidence < 3:
        limitations.append("Limited evidence retrieved — results may be incomplete")

    # Patient profile snapshot for API response
    profile_summary: dict = {}
    if patient_profile:
        profile_summary = {
            "full_name": patient_profile.full_name,
            "date_of_birth": patient_profile.date_of_birth,
            "gender": patient_profile.gender,
            "target_drug": patient_profile.target_drug,
            "patient_factors": patient_profile.patient_factors,
            "comorbidities": patient_profile.comorbidities,
            "current_medications": patient_profile.current_medications,
            "allergies": patient_profile.allergies,
            "age_range": patient_profile.age_range,
            "kidney_function": patient_profile.kidney_function,
            "pregnancy_trimester": patient_profile.pregnancy_trimester,
        }

    response = StructuredResponse(
        query=query,
        query_category=state.get("query_category", ""),
        interaction_mode=interaction_mode,
        clinical_context_summary=" | ".join(ctx_parts),
        detected_drugs=context.drugs,
        detected_diseases=context.diseases,
        detected_patient_factors=context.patient_factors,
        drug_evidence_summary=_summarize_drug_evidence(drug_evidence),
        retrieved_evidence=drug_evidence,
        risk_findings=risk_findings,
        drug_overview=drug_overview,
        main_response=draft,
        key_points=key_points,
        key_warnings=key_warnings,
        evidence_limitations=limitations,
        citations=citations[:15],
        grounded_claims=grounded,
        evidence_quality=evidence_quality,
        safety_assessment=safety,
        disclaimer=STANDARD_DISCLAIMER if interaction_mode != InteractionMode.CHAT_QUERY.value else "",
        execution_trace=trace,
        patient_profile_summary=profile_summary,
    )

    logger.info(
        "response_formatted",
        valid_citations=valid_citations,
        invalid_citations=len(invalid_citations),
        evidence_quality=evidence_quality,
        category=state.get("query_category", ""),
        risk_findings=len(risk_findings),
    )

    return {
        **state,
        "final_response": response,
        "grounded_claims": grounded,
        "safety_assessment": safety,
        "execution_trace": trace,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _summarize_drug_evidence(chunks: list[EvidenceChunk]) -> str:
    """Create a brief summary of drug sources used."""
    if not chunks:
        return "No drug evidence retrieved."
    drugs = {c.drug_name for c in chunks if c.drug_name}
    sections = {c.section_type for c in chunks if c.section_type}
    return f"Retrieved {len(chunks)} drug evidence chunks for: {', '.join(drugs)} ({', '.join(str(s) for s in sections)})"


# ═══════════════════════════════════════════════════════════════════════════════
# Special Nodes: Out-of-scope, ambiguous, refusal
# ═══════════════════════════════════════════════════════════════════════════════

def out_of_scope_response(state: MedResolveState) -> MedResolveState:
    """Handle out-of-scope queries."""
    context = state.get("clinical_context") or ClinicalContext()
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("out_of_scope_response")

    msg = OUT_OF_SCOPE_TEMPLATE.format(
        query=state["query"],
        reason=context.clinical_intent or "Query falls outside the supported drug knowledge base scope"
    )

    response = StructuredResponse(
        query=state["query"],
        query_category=QueryCategory.OUT_OF_SCOPE.value,
        main_response=msg,
        is_refused=True,
        refusal_reason="Out of scope",
        disclaimer=STANDARD_DISCLAIMER,
        execution_trace=trace,
    )
    return {**state, "final_response": response, "execution_trace": trace}


def ambiguous_response(state: MedResolveState) -> MedResolveState:
    """Handle ambiguous queries by asking for clarification."""
    context = state.get("clinical_context") or ClinicalContext()
    trace = state.get("execution_trace") or ExecutionTrace()
    trace.processing_steps.append("ambiguous_response")

    points = []
    if not context.drugs:
        points.append("- Which drug are you asking about? (e.g. lisinopril, metformin, atorvastatin)")
    if context.drugs and not context.diseases and not context.patient_factors:
        points.append("- What is the clinical context? (e.g. patient with renal impairment, pregnancy, diabetes)")
    if not points:
        points.append("- Could you provide more clinical context about the drug and patient scenario?")

    msg = AMBIGUOUS_TEMPLATE.format(
        query=state["query"],
        clarification_points="\n".join(points),
    )

    response = StructuredResponse(
        query=state["query"],
        query_category=QueryCategory.AMBIGUOUS.value,
        main_response=msg,
        disclaimer=STANDARD_DISCLAIMER,
        execution_trace=trace,
    )
    return {**state, "final_response": response, "execution_trace": trace}
