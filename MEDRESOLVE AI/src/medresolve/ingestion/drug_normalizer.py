"""
MEDRESOLVE AI — Drug Knowledge Base Normalizer
Handles both Schema A (full profiles) and Schema B (raw openFDA) drug files,
producing unified DrugChunk objects ready for vector indexing.

New chunking strategy: 7-12 fine-grained per-factor sub-chunks per drug
instead of 4 mega-chunks. This dramatically improves retrieval precision.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional
import structlog

logger = structlog.get_logger(__name__)

# ─── Known drug aliases for name normalization ─────────────────────────────────
DRUG_ALIASES: dict[str, list[str]] = {
    "lisinopril": ["lisinopril", "prinivil", "zestril", "qbrelis"],
    "losartan": ["losartan", "cozaar"],
    "amlodipine": ["amlodipine", "norvasc"],
    "metformin": ["metformin", "glucophage", "fortamet", "glumetza", "riomet"],
    "insulin_glargine": ["insulin glargine", "lantus", "basaglar", "toujeo"],
    "atorvastatin": ["atorvastatin", "lipitor"],
    "warfarin": ["warfarin", "coumadin", "jantoven"],
    "labetalol": ["labetalol", "trandate"],
    "methyldopa": ["methyldopa", "aldomet"],
    "metoprolol": ["metoprolol", "lopressor", "toprol"],
    "hydrochlorothiazide": ["hydrochlorothiazide", "hctz", "microzide"],
    "rosuvastatin": ["rosuvastatin", "crestor"],
    "simvastatin": ["simvastatin", "zocor"],
}

# ─── Clinical relevance tiers ─────────────────────────────────────────────────
CLINICAL_RELEVANCE = {
    # Tier 1: Core HTN/DM/CVD/CKD scope
    "lisinopril": "tier1_core",
    "losartan": "tier1_core",
    "amlodipine": "tier1_core",
    "labetalol": "tier1_core",
    "methyldopa": "tier1_core",
    "metformin": "tier1_core",
    "insulin_glargine": "tier1_core",
    "atorvastatin": "tier1_core",
    "warfarin": "tier1_core",
    "hydrochlorothiazide": "tier1_core",
    "metoprolol": "tier1_core",
    "rosuvastatin": "tier1_core",
    "simvastatin": "tier1_core",
    # Tier 2: Supporting safety / pregnancy
    "ibuprofen": "tier2_supporting",
    "doxycycline": "tier2_supporting",
    "nitrofurantoin": "tier2_supporting",
    "methimazole": "tier2_supporting",
    "levothyroxine": "tier2_supporting",
    "sertraline": "tier2_supporting",
    "folic_acid": "tier2_supporting",
    "amoxicillin": "tier2_supporting",
    "cephalexin": "tier2_supporting",
    "fluconazole": "tier2_supporting",
    # Tier 3: Benchmark safety evaluation
    "methotrexate": "tier3_benchmark",
    "valproic_acid": "tier3_benchmark",
    "isotretinoin": "tier3_benchmark",
    "thalidomide": "tier3_benchmark",
    "misoprostol": "tier3_benchmark",
    "leflunomide": "tier3_benchmark",
}

# ─── Patient factor detection patterns ────────────────────────────────────────
FACTOR_PATTERNS: dict[str, str] = {
    "Renal Impairment / Kidney": r"\b(?:renal|kidney|CKD|GFR|creatinine|dialysis|eGFR|nephro)\b",
    "Hepatic Impairment / Liver": r"\b(?:hepatic|liver|hepatotoxicity|cirrhosis|hepat)\b",
    "Pregnancy / Teratogenicity": r"\b(?:pregnan|fetal|teratogen|embryo|maternal|trimester|gestational)\b",
    "Lactation / Breastfeeding": r"\b(?:lact|breast.?feed|nursing|breast\s*milk)\b",
    "Age (Geriatric / Elderly)": r"\b(?:geriatric|elderly|older\s+adult|aged?\s+\d+|65\s+years?)\b",
    "Age (Pediatric / Children)": r"\b(?:pediatric|children|child|infant|neonate|adolescent)\b",
    "Diabetes / Glycemic Control": r"\b(?:diabet|glycem|insulin|glucose|HbA1c|hyperglycemia)\b",
    "Cardiovascular / Arrhythmia": r"\b(?:cardiovascular|cardiac|heart|arrhythmia|MI|stroke|QT)\b",
    "Weight / Obesity / BMI": r"\b(?:obese|obesity|weight|BMI|overweight)\b",
    "Hypertension": r"\b(?:hypertens|blood\s*pressure|antihypertens)\b",
}


@dataclass
class DrugChunk:
    """A processed drug evidence chunk ready for vector indexing."""
    chunk_id: str
    drug_id: str
    drug_name: str
    aliases: list[str]
    primary_indication: str
    category: str
    tier: str
    clinical_relevance: str
    section_type: str          # BOXED_WARNING | CONTRAINDICATIONS | PREGNANCY | RENAL | etc.
    target_patient_factors: list[str]
    content: str
    word_count: int
    source_type: str = "drug_evidence"
    has_boxed_warning: bool = False
    has_contraindications: bool = False
    data_source: str = "DailyMed (NLM/NIH) + openFDA"
    schema_version: str = "A"  # "A" = full profile, "B" = raw openFDA


# ─── Placeholder text patterns (P0 fix) ──────────────────────────────────────
# These are known non-informative strings that appear in the raw KB data.
# They must NOT be indexed as real content and must NOT set safety flags.
_PLACEHOLDER_PATTERNS: tuple[str, ...] = (
    "no boxed warning specified in label.",
    "no boxed warning specified in label",
    "no boxed warning.",
    "no boxed warning",
    "data not provided.",
    "data not provided",
    "contraindications not explicitly detailed.",
    "contraindications not explicitly detailed",
    "not specified.",
    "not specified",
    "no information available.",
    "no information available",
    "n/a",
    "not applicable",
)

# Regex for structured "None." patterns (e.g. "### 4 CONTRAINDICATIONS\nNone.\nNone.")
_NONE_ONLY_RE = re.compile(
    r"^(?:#{1,6}\s*\d*\s*\w[\w\s]*\n+)?\s*(?:none\.?\s*)+$",
    re.IGNORECASE | re.MULTILINE,
)


def _is_placeholder(text: str) -> bool:
    """
    Return True if `text` is a non-informative placeholder that should NOT
    be indexed as a real chunk and should NOT trigger safety flags.

    Covers patterns found in the real knowledge base:
      - "No boxed warning specified in label."
      - "No boxed warning."
      - "Data not provided."
      - "Contraindications not explicitly detailed."
      - "Not specified."
      - "None." / "None.\nNone." (including with section headings)
      - Empty or whitespace-only strings
    """
    if not text or not text.strip():
        return True
    normalised = text.strip().lower()
    # Check against known exact/prefix patterns
    if normalised in _PLACEHOLDER_PATTERNS:
        return True
    # Check None-only pattern (handles "### 4 CONTRAINDICATIONS\nNone.\nNone.")
    if _NONE_ONLY_RE.match(text.strip()):
        return True
    # Very short text that is not a real clinical statement (< 20 chars)
    if len(text.strip()) < 20:
        return True
    return False


def _sentence_split_at(text: str, max_chars: int = 1500) -> str:
    """
    Trim text to at most max_chars characters, breaking at the last
    sentence boundary (period/question mark/exclamation) before the limit.
    Much cleaner than hard-cutting mid-sentence.
    """
    if len(text) <= max_chars:
        return text
    # Find last sentence boundary before max_chars
    truncated = text[:max_chars]
    last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_period > max_chars // 2:
        return truncated[: last_period + 1].strip()
    return truncated.strip()


def _detect_patient_factors(text: str) -> list[str]:
    """Detect which patient factors are mentioned in text."""
    found = []
    for factor, pattern in FACTOR_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            found.append(factor)
    return found


def _to_drug_id(drug_name: str) -> str:
    """Convert drug name to snake_case drug_id."""
    name = drug_name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name


def _tokenize_bm25(text: str) -> list[str]:
    """
    Medical-aware BM25 tokenization.
    Strips punctuation, lowercases, handles medical abbreviations properly.
    e.g. 'eGFR<30' -> ['egfr', '30'], '(lisinopril)' -> ['lisinopril']
    """
    # Lowercase
    text = text.lower()
    # Split on whitespace and non-alphanumeric chars (keep hyphenated terms)
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text)
    # Remove single-character tokens except meaningful ones (e.g. 'a', 'b')
    tokens = [t for t in tokens if len(t) > 1 or t.isdigit()]
    return tokens


class DrugNormalizer:
    """
    Normalizes drug data from two different schemas into unified DrugChunk objects.
    Schema A: Full processed profiles (master_knowledge_base.json / individual files)
    Schema B: Raw openFDA extractions (individual *.json files)

    NEW CHUNKING STRATEGY:
    Instead of 4 mega-chunks per drug, produces 7-12 fine-grained per-factor chunks:
    BOXED_WARNING, CONTRAINDICATIONS, WARNINGS_AND_PRECAUTIONS, DRUG_INTERACTIONS,
    PREGNANCY, LACTATION, PEDIATRIC_USE, GERIATRIC_USE, RENAL_IMPAIRMENT,
    HEPATIC_IMPAIRMENT, DOSAGE_AND_ADMINISTRATION, DRUG_OVERVIEW
    """

    def __init__(self, drug_kb_dir: Path):
        self.drug_kb_dir = drug_kb_dir

    # Minimum number of fine-grained master-KB chunks a drug must have before
    # rag_chunks.json coarse fallback chunks are suppressed for that drug.
    # Fine-grained chunks (BOXED_WARNING, CONTRAINDICATIONS, PREGNANCY, RENAL, …)
    # are 40-235 words each and are section-specific.  Coarse rag_chunks.json
    # mega-chunks (CONTRAINDICATIONS_AND_WARNINGS, INTERACTIONS_AND_PHARMACOLOGY,
    # PATIENT_POPULATIONS_AND_DEMOGRAPHICS) are 900-1800 words and span multiple
    # clinical concepts.  When both exist for the same drug they compete during
    # BM25 scoring (longer docs → higher raw score) and cross-encoder ranking
    # (more text → more query terms hit), pushing focused relevant chunks below
    # rank 1.  Suppressing the coarse chunks for well-covered drugs removes
    # ~123 competing mega-chunks and is the primary ranking fix.
    _MIN_FINE_CHUNKS_TO_SUPPRESS_COARSE: int = 3

    def load_all_chunks(self) -> list[DrugChunk]:
        """Load all available drug data and produce unified per-factor chunks."""
        all_chunks: list[DrugChunk] = []
        seen_chunk_ids: set[str] = set()

        # 1. Load Schema A drugs from master_knowledge_base.json (best quality)
        master_path = self.drug_kb_dir / "master_knowledge_base.json"
        if master_path.exists():
            schema_a_chunks = self._load_schema_a_master(master_path)
            for chunk in schema_a_chunks:
                if chunk.chunk_id not in seen_chunk_ids:
                    all_chunks.append(chunk)
                    seen_chunk_ids.add(chunk.chunk_id)
            logger.info("schema_a_master_loaded", count=len(schema_a_chunks))

        # 2. Build per-drug fine-grained chunk count BEFORE loading rag fallback.
        #    This is used inside _load_schema_a_rag_chunks_fallback to suppress
        #    coarse mega-chunks for drugs that are already well-covered.
        fine_chunk_counts: dict[str, int] = {}
        for chunk in all_chunks:
            fine_chunk_counts[chunk.drug_id] = fine_chunk_counts.get(chunk.drug_id, 0) + 1

        # 3. Also check rag_chunks.json for any drugs not yet covered by master KB.
        #    Drugs with >= _MIN_FINE_CHUNKS_TO_SUPPRESS_COARSE fine-grained chunks
        #    will have their coarse rag_chunks.json entries skipped.
        rag_path = self.drug_kb_dir / "rag_chunks.json"
        if rag_path.exists():
            extra_chunks = self._load_schema_a_rag_chunks_fallback(
                rag_path, seen_chunk_ids, fine_chunk_counts
            )
            all_chunks.extend(extra_chunks)
            if extra_chunks:
                logger.info("rag_chunks_fallback_loaded", count=len(extra_chunks))

        # 4. Load Schema B drugs (raw individual JSON files not in master KB)
        schema_b_chunks = self._load_schema_b_drugs(seen_chunk_ids)
        all_chunks.extend(schema_b_chunks)
        logger.info("schema_b_loaded", count=len(schema_b_chunks))

        # Log per-drug distribution
        drug_counts: dict[str, int] = {}
        for c in all_chunks:
            drug_counts[c.drug_id] = drug_counts.get(c.drug_id, 0) + 1
        logger.info(
            "chunk_distribution",
            total=len(all_chunks),
            drugs=len(drug_counts),
            avg_per_drug=round(len(all_chunks) / max(len(drug_counts), 1), 1),
        )
        return all_chunks

    # ── Schema A: Master Knowledge Base ───────────────────────────────────────

    def _load_schema_a_master(self, master_path: Path) -> list[DrugChunk]:
        """
        Load from master_knowledge_base.json and generate per-factor sub-chunks.
        This is the primary high-quality source.
        """
        with open(master_path, encoding="utf-8") as f:
            master_data = json.load(f)

        chunks: list[DrugChunk] = []
        for entry in master_data:
            drug_id = entry.get("drug_id", "")
            if not drug_id:
                continue
            drug_chunks = self._generate_schema_a_chunks(drug_id, entry)
            chunks.extend(drug_chunks)

        return chunks

    def _generate_schema_a_chunks(self, drug_id: str, entry: dict) -> list[DrugChunk]:
        """
        Generate fine-grained per-factor chunks from a Schema A master KB entry.
        Produces up to 12 focused chunks instead of 4 mega-chunks.
        """
        drug_name = entry.get("drug_name", drug_id.replace("_", " ").title())
        aliases = entry.get("aliases", [drug_name])
        primary_indication = entry.get("primary_indication", "")
        category = entry.get("category", "")
        tier = entry.get("tier", "")
        clinical_relevance = CLINICAL_RELEVANCE.get(drug_id, "tier4_other")
        all_factor_tags = entry.get("all_patient_factor_tags", [])

        safety = entry.get("patient_safety_guardrails", {})
        populations = entry.get("patient_population_profiles", {})
        clinical = entry.get("clinical_usage_guidance", {})
        faers = entry.get("top_adverse_events_faers", [])
        pharm_class = entry.get("pharmacologic_class", "")
        known_risks = entry.get("known_critical_risks", [])

        base_meta = dict(
            drug_id=drug_id,
            drug_name=drug_name,
            aliases=aliases,
            primary_indication=primary_indication,
            category=category,
            tier=tier,
            clinical_relevance=clinical_relevance,
            data_source="DailyMed (NLM/NIH) + openFDA",
            schema_version="A",
        )

        # P0-A fix: use _is_placeholder() to avoid false True for non-informative text
        # e.g. "No boxed warning specified in label." must NOT set has_boxed_warning=True
        has_boxed_warning = bool(safety.get("boxed_warning", "")) and not _is_placeholder(
            safety.get("boxed_warning", "")
        )
        has_contraindications = bool(safety.get("contraindications", "")) and not _is_placeholder(
            safety.get("contraindications", "")
        )

        chunks: list[DrugChunk] = []

        # ── 1. Boxed Warning chunk ─────────────────────────────────────────
        bw = safety.get("boxed_warning", "")
        # P0-B fix: use _is_placeholder() instead of narrow exact-match check
        if bw and not _is_placeholder(bw):
            content = f"# BOXED WARNING: {drug_name}\n\n{_sentence_split_at(bw, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_boxed_warning",
                section_type="BOXED_WARNING",
                target_patient_factors=_detect_patient_factors(content) or all_factor_tags,
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=True,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        # ── 2. Contraindications chunk ────────────────────────────────────
        ci = safety.get("contraindications", "")
        # P0-B fix: use _is_placeholder() instead of narrow exact-match check
        if ci and not _is_placeholder(ci):
            content = f"# Contraindications: {drug_name}\n\n{_sentence_split_at(ci, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_contraindications",
                section_type="CONTRAINDICATIONS",
                target_patient_factors=_detect_patient_factors(content) or all_factor_tags,
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=True,
                **base_meta,
            ))

        # ── 3. Warnings & Precautions chunk ──────────────────────────────
        wp = safety.get("warnings_and_precautions", "")
        # P0-B fix: use _is_placeholder() for consistent placeholder detection
        if wp and not _is_placeholder(wp):
            content = f"# Warnings and Precautions: {drug_name}\n\n{_sentence_split_at(wp, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_warnings_precautions",
                section_type="WARNINGS_AND_PRECAUTIONS",
                target_patient_factors=_detect_patient_factors(content) or all_factor_tags,
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        # ── 4. Drug Interactions chunk ────────────────────────────────────
        di = safety.get("drug_interactions", "")
        # P0-B fix: use _is_placeholder() for consistent placeholder detection
        if di and not _is_placeholder(di):
            content = f"# Drug Interactions: {drug_name}\n\n{_sentence_split_at(di, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_drug_interactions",
                section_type="DRUG_INTERACTIONS",
                target_patient_factors=_detect_patient_factors(content),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 5. Pregnancy chunk ────────────────────────────────────────────
        preg = populations.get("pregnancy_and_teratogenicity", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if preg and not _is_placeholder(preg):
            content = f"# Pregnancy & Teratogenicity: {drug_name}\n\n{_sentence_split_at(preg, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_pregnancy",
                section_type="PREGNANCY",
                target_patient_factors=["Pregnancy / Teratogenicity"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications="contraindicated" in preg.lower() and "pregnancy" in preg.lower(),
                **base_meta,
            ))

        # ── 6. Lactation chunk ────────────────────────────────────────────
        lact = populations.get("lactation_and_nursing", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if lact and not _is_placeholder(lact):
            content = f"# Lactation & Breastfeeding: {drug_name}\n\n{_sentence_split_at(lact, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_lactation",
                section_type="LACTATION",
                target_patient_factors=["Lactation / Breastfeeding"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 7. Pediatric use chunk ────────────────────────────────────────
        peds = populations.get("pediatric_use", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if peds and not _is_placeholder(peds):
            content = f"# Pediatric Use: {drug_name}\n\n{_sentence_split_at(peds, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_pediatric",
                section_type="PEDIATRIC_USE",
                target_patient_factors=["Age (Pediatric / Children)"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 8. Geriatric use chunk ────────────────────────────────────────
        geri = populations.get("geriatric_use", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if geri and not _is_placeholder(geri):
            content = f"# Geriatric Use (Elderly Patients): {drug_name}\n\n{_sentence_split_at(geri, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_geriatric",
                section_type="GERIATRIC_USE",
                target_patient_factors=["Age (Geriatric / Elderly)"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 9. Renal Impairment chunk ─────────────────────────────────────
        renal = populations.get("renal_impairment", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if renal and not _is_placeholder(renal):
            content = f"# Renal Impairment / Kidney Disease: {drug_name}\n\n{_sentence_split_at(renal, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_renal",
                section_type="RENAL_IMPAIRMENT",
                target_patient_factors=["Renal Impairment / Kidney"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 10. Hepatic Impairment chunk ──────────────────────────────────
        hepatic = populations.get("hepatic_impairment", "")
        # P0-CHUNK-2 fix: use _is_placeholder() to reject non-informative text
        if hepatic and not _is_placeholder(hepatic):
            content = f"# Hepatic Impairment / Liver Disease: {drug_name}\n\n{_sentence_split_at(hepatic, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_hepatic",
                section_type="HEPATIC_IMPAIRMENT",
                target_patient_factors=["Hepatic Impairment / Liver"],
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 11. Dosage & Administration chunk ────────────────────────────
        dosage_sections = clinical if isinstance(clinical, dict) else {}
        dosage_text = dosage_sections.get("dosage_and_administration", "") or dosage_sections.get("dosage", "")
        if not dosage_text:
            # Fallback: try to get from clinical_sections
            clinical_secs = entry.get("clinical_sections", {})
            dosage_text = clinical_secs.get("dosage_and_administration", "")

        if dosage_text and not _is_placeholder(str(dosage_text)):
            content = f"# Dosage & Administration: {drug_name}\n\n{_sentence_split_at(str(dosage_text), 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_dosage",
                section_type="DOSAGE_AND_ADMINISTRATION",
                target_patient_factors=_detect_patient_factors(str(dosage_text)),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # ── 12. Drug Overview chunk ───────────────────────────────────────
        overview_parts = [f"# Drug Overview: {drug_name}"]
        if pharm_class:
            overview_parts.append(f"\n**Pharmacologic Class**: {pharm_class}")
        if primary_indication:
            overview_parts.append(f"\n**Primary Indication**: {primary_indication}")
        # Add mechanism from clinical sections if available
        cs = entry.get("clinical_sections", {})
        moa = cs.get("mechanism_of_action", "") or cs.get("clinical_pharmacology", "")
        if moa:
            overview_parts.append(f"\n**Mechanism**: {_sentence_split_at(str(moa), 600)}")
        if known_risks:
            overview_parts.append(f"\n**Known Critical Risks**: {'; '.join(str(r) for r in known_risks[:5])}")
        if faers:
            top_ae = [str(e) for e in faers[:5] if e]
            if top_ae:
                overview_parts.append(f"\n**Top Adverse Events (FAERS)**: {', '.join(top_ae)}")

        overview_content = "\n".join(overview_parts)
        if len(overview_content) > 100:  # Only create if meaningful
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_overview",
                section_type="DRUG_OVERVIEW",
                target_patient_factors=all_factor_tags or [],
                content=overview_content,
                word_count=len(overview_content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        return chunks

    # ── Schema A: Fallback RAG chunks ─────────────────────────────────────────

    def _load_schema_a_rag_chunks_fallback(
        self,
        rag_path: Path,
        seen_ids: set[str],
        fine_chunk_counts: dict[str, int] | None = None,
    ) -> list[DrugChunk]:
        """
        Load pre-built RAG chunks from rag_chunks.json as a fallback
        for any drugs NOT already covered by the master KB.

        Suppression rule (P0 ranking fix):
        If a drug already has >= _MIN_FINE_CHUNKS_TO_SUPPRESS_COARSE fine-grained
        chunks from the master KB (as reported in `fine_chunk_counts`), its
        rag_chunks.json entries are skipped entirely.  Those entries are coarse
        mega-chunks (900-1800 words spanning multiple clinical sections) that
        compete with and outrank the focused fine-grained chunks (40-235 words)
        during BM25 and cross-encoder ranking.

        Only drugs with < _MIN_FINE_CHUNKS_TO_SUPPRESS_COARSE fine-grained chunks
        (i.e. drugs absent from the master KB) get their rag_chunks.json data
        loaded, preserving full coverage for those drugs.
        """
        threshold = self._MIN_FINE_CHUNKS_TO_SUPPRESS_COARSE
        counts = fine_chunk_counts or {}

        with open(rag_path, encoding="utf-8") as f:
            raw_chunks = json.load(f)

        suppressed_drugs: set[str] = set()
        chunks = []
        for raw in raw_chunks:
            chunk_id = raw.get("chunk_id", "")
            if chunk_id in seen_ids:
                continue  # Already have a better version from master KB

            drug_name = raw.get("drug_name", "")
            drug_id = self._to_drug_id_static(drug_name)

            # ── P0 suppression: skip coarse chunks for well-covered drugs ──────
            if counts.get(drug_id, 0) >= threshold:
                suppressed_drugs.add(drug_id)
                continue

            chunk = DrugChunk(
                chunk_id=chunk_id,
                drug_id=drug_id,
                drug_name=drug_name,
                aliases=DRUG_ALIASES.get(drug_id, [drug_name]),
                primary_indication="",
                category=raw.get("category", ""),
                tier=raw.get("tier", ""),
                clinical_relevance=CLINICAL_RELEVANCE.get(drug_id, "tier4_other"),
                section_type=raw.get("section_type", ""),
                target_patient_factors=raw.get("target_patient_factors", []),
                content=raw.get("content", ""),
                word_count=raw.get("word_count", len(raw.get("content", "").split())),
                has_boxed_warning=False,
                has_contraindications=False,
                data_source="DailyMed (NLM/NIH) + openFDA",
                schema_version="A-fallback",
            )
            chunks.append(chunk)

        if suppressed_drugs:
            logger.info(
                "coarse_chunks_suppressed",
                reason="drug_already_has_fine_grained_master_kb_chunks",
                suppressed_drug_count=len(suppressed_drugs),
                threshold=threshold,
                drugs=sorted(suppressed_drugs),
            )

        return chunks

    # ── Schema B: Raw openFDA individual JSON files ───────────────────────────

    def _load_schema_b_drugs(self, seen_ids: set[str]) -> list[DrugChunk]:
        """
        Dynamically discover all *.json files in KB directory and load
        drugs not already covered by Schema A. No hardcoded list.
        """
        skip_files = {
            "master_knowledge_base.json",
            "rag_chunks.json",
            "extraction_report.json",
        }

        chunks: list[DrugChunk] = []
        for drug_file in sorted(self.drug_kb_dir.glob("*.json")):
            if drug_file.name in skip_files:
                continue

            drug_id = drug_file.stem  # filename without .json

            # Skip if already well-covered by Schema A (has 3+ chunks)
            existing = sum(1 for cid in seen_ids if cid.startswith(f"{drug_id}_"))
            if existing >= 3:
                continue

            try:
                with open(drug_file, encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                logger.debug("schema_b_read_error", drug_id=drug_id, error=str(e))
                continue

            # Skip skeleton profiles (no label info)
            label_info = raw.get("label_clinical_info", {})
            if not label_info or not any(
                v and v != "Data not provided." and len(str(v)) > 20
                for v in label_info.values()
            ):
                logger.debug("skipping_skeleton", drug_id=drug_id)
                continue

            drug_chunks = self._generate_schema_b_chunks(drug_id, raw)
            for chunk in drug_chunks:
                if chunk.chunk_id not in seen_ids:
                    chunks.append(chunk)
                    seen_ids.add(chunk.chunk_id)

        return chunks

    def _generate_schema_b_chunks(self, drug_id: str, raw: dict) -> list[DrugChunk]:
        """
        Generate fine-grained per-factor chunks from a Schema B raw drug profile.
        Produces up to 8 focused chunks per drug.
        """
        label_info = raw.get("label_clinical_info", {})
        drug_name = raw.get("generic_name") or raw.get("brand_name") or raw.get("search_query", drug_id)
        drug_name = drug_name.strip().title() if drug_name else drug_id.replace("_", " ").title()

        aliases = [drug_name]
        if known := DRUG_ALIASES.get(drug_id):
            aliases = [a.title() for a in known]

        base_meta = dict(
            drug_id=drug_id,
            drug_name=drug_name,
            aliases=aliases,
            primary_indication=self._extract_indication(label_info),
            category="Schema B Drug",
            tier="Raw Profile",
            clinical_relevance=CLINICAL_RELEVANCE.get(drug_id, "tier4_other"),
            data_source="DailyMed (NLM/NIH) + openFDA",
            schema_version="B",
        )

        chunks: list[DrugChunk] = []
        bw_raw = label_info.get("boxed_warning", "")
        ci_raw = label_info.get("contraindications", "")
        wp_raw = label_info.get("warnings_and_precautions", "")
        di_raw = label_info.get("drug_interactions", "")
        da_raw = label_info.get("dosage_and_administration", "")
        ind_raw = label_info.get("indications_and_usage", "")
        moa_raw = label_info.get("mechanism_of_action", "")

        # P0-A fix: use module-level _is_placeholder() for accurate flag assignment
        has_boxed_warning = bool(bw_raw) and not _is_placeholder(bw_raw)
        has_contraindications = bool(ci_raw) and not _is_placeholder(ci_raw)

        def _is_valid(text: str) -> bool:
            # P0-B fix: delegate to module-level _is_placeholder() for consistency
            return bool(text) and not _is_placeholder(text)

        # 1. Boxed Warning
        if _is_valid(bw_raw):
            content = f"# ⚠️ BOXED WARNING: {drug_name}\n\n{_sentence_split_at(bw_raw, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_boxed_warning",
                section_type="BOXED_WARNING",
                target_patient_factors=_detect_patient_factors(content),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=True,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        # 2. Contraindications
        if _is_valid(ci_raw):
            content = f"# Contraindications: {drug_name}\n\n{_sentence_split_at(ci_raw, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_contraindications",
                section_type="CONTRAINDICATIONS",
                target_patient_factors=_detect_patient_factors(content),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=True,
                **base_meta,
            ))

        # 3. Warnings & Precautions
        if _is_valid(wp_raw):
            content = f"# Warnings and Precautions: {drug_name}\n\n{_sentence_split_at(wp_raw, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_warnings_precautions",
                section_type="WARNINGS_AND_PRECAUTIONS",
                target_patient_factors=_detect_patient_factors(content),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        # 4. Drug Interactions
        if _is_valid(di_raw):
            content = f"# Drug Interactions: {drug_name}\n\n{_sentence_split_at(di_raw, 1500)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_drug_interactions",
                section_type="DRUG_INTERACTIONS",
                target_patient_factors=_detect_patient_factors(content),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # 5. Population-specific info from dosage/indications text
        da_combined = (da_raw or "") + " " + (ind_raw or "")
        pop_parts: list[str] = [f"# Special Patient Populations: {drug_name}"]
        factor_keywords = {
            "Pregnancy / Teratogenicity": ["pregnan", "trimester", "fetal", "teratogen"],
            "Renal Impairment / Kidney": ["renal", "kidney", "egfr", "dialysis"],
            "Hepatic Impairment / Liver": ["hepatic", "liver", "cirrhosis"],
            "Age (Geriatric / Elderly)": ["geriatric", "elderly", "65 year", "older adult"],
            "Age (Pediatric / Children)": ["pediatric", "children", "infant"],
        }
        found_factors: list[str] = []
        for factor, keywords in factor_keywords.items():
            kw_sentences = []
            for kw in keywords:
                # P2-A fix: split only at sentence boundaries (period/!/?  followed by
                # whitespace + uppercase) to avoid fragmenting dosage numbers like "2.5 mg"
                for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", da_combined):
                    sent = sent.strip()
                    # Skip fragments shorter than 20 chars (broken numeric splits, etc.)
                    if kw in sent.lower() and len(sent) >= 20 and sent not in kw_sentences:
                        kw_sentences.append(sent)
            if kw_sentences:
                found_factors.append(factor)
                pop_parts.append(f"\n## {factor}\n" + ". ".join(kw_sentences[:3]))

        if len(pop_parts) > 1:
            content = "\n".join(pop_parts)
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_special_populations",
                section_type="PATIENT_POPULATIONS_AND_DEMOGRAPHICS",
                target_patient_factors=found_factors,
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # 6. Dosage & Administration
        if _is_valid(da_raw):
            content = f"# Dosage & Administration: {drug_name}\n\n{_sentence_split_at(da_raw, 1500)}"
            if _is_valid(ind_raw):
                content += f"\n\n## Indications\n{_sentence_split_at(ind_raw, 600)}"
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_dosage",
                section_type="DOSAGE_AND_ADMINISTRATION",
                target_patient_factors=_detect_patient_factors(da_raw),
                content=content,
                word_count=len(content.split()),
                has_boxed_warning=False,
                has_contraindications=False,
                **base_meta,
            ))

        # 7. Drug Overview
        overview_parts = [f"# Drug Overview: {drug_name}"]
        if _is_valid(ind_raw):
            overview_parts.append(f"\n**Indication**: {_sentence_split_at(ind_raw, 400)}")
        if _is_valid(moa_raw):
            overview_parts.append(f"\n**Mechanism**: {_sentence_split_at(moa_raw, 400)}")
        pharm = raw.get("pharmacologic_class", "")
        if pharm:
            overview_parts.append(f"\n**Drug Class**: {pharm}")

        overview_content = "\n".join(overview_parts)
        if len(overview_content) > 80:
            chunks.append(DrugChunk(
                chunk_id=f"{drug_id}_overview",
                section_type="DRUG_OVERVIEW",
                target_patient_factors=[],
                content=overview_content,
                word_count=len(overview_content.split()),
                has_boxed_warning=has_boxed_warning,
                has_contraindications=has_contraindications,
                **base_meta,
            ))

        return chunks

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_indication(self, label_info: dict) -> str:
        """Extract primary indication from label info."""
        ind = label_info.get("indications_and_usage", "")
        if not ind or ind == "Data not provided.":
            return "Unknown"
        return ind[:200].split(".")[0].strip()

    @staticmethod
    def _to_drug_id_static(drug_name: str) -> str:
        return _to_drug_id(drug_name)
