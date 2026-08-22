"""
MEDRESOLVE AI — RAG Evaluation Suite v1.0
==========================================
Real retrieval metrics for the hybrid RAG pipeline:

  Retrieval Metrics (per-query & aggregate):
    * Precision@k   — fraction of top-k results that are relevant
    * Recall@k      — fraction of relevant docs found in top-k
    * F1@k          — harmonic mean of Precision@k and Recall@k
    * MRR           — Mean Reciprocal Rank (first relevant result)
    * NDCG@k        — Normalized Discounted Cumulative Gain (graded)
    * Hit Rate@k    — 1 if any relevant doc in top-k, else 0
    * Average Rank  — mean rank of first relevant result

Usage:
    python eval/rag_eval.py [--k 1 3 5 10] [--section A|B|C|all] [--save-html]
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog

from medresolve.retrieval.hybrid_retriever import build_retriever, HybridRetriever
from medresolve.models import EvidenceChunk

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 1.  Ground-truth relevance labels
#     Each entry: query_id -> list of (drug_id, section_type, grade)
#     grade: 3=critical safety, 2=important clinical, 1=supporting info
#     A retrieved chunk is "relevant" when drug_id AND section_type both match.
# ---------------------------------------------------------------------------

RETRIEVAL_GROUND_TRUTH: dict[str, list[tuple[str, str, int]]] = {
    # P0-EVAL-1 fix: Updated to use the actual 12 fine-grained section types
    # produced by the current chunking pipeline (drug_normalizer.py).
    # Previously used 4 coarse types with a lossy SECTION_NORMALIZATION mapping
    # that inflated metrics by collapsing DRUG_OVERVIEW into INTERACTIONS_AND_PHARMACOLOGY.
    #
    # Actual section types in ChromaDB:
    #   BOXED_WARNING, CONTRAINDICATIONS, WARNINGS_AND_PRECAUTIONS,
    #   DRUG_INTERACTIONS, PREGNANCY, LACTATION, PEDIATRIC_USE, GERIATRIC_USE,
    #   RENAL_IMPAIRMENT, HEPATIC_IMPAIRMENT, DOSAGE_AND_ADMINISTRATION, DRUG_OVERVIEW
    #
    # P1-EVAL-3 fix: valproic_acid drug_id corrected (was valproic_acid_sodium_valproate)

    # ── Section A: Risk Report queries ─────────────────────────────────────────
    "RR_01": [("lisinopril","CONTRAINDICATIONS",3),("lisinopril","RENAL_IMPAIRMENT",3),("lisinopril","WARNINGS_AND_PRECAUTIONS",2),("lisinopril","DOSAGE_AND_ADMINISTRATION",1)],
    "RR_02": [("metformin","BOXED_WARNING",3),("metformin","CONTRAINDICATIONS",3),("metformin","RENAL_IMPAIRMENT",3),("metformin","DOSAGE_AND_ADMINISTRATION",2)],
    "RR_03": [("labetalol","PREGNANCY",3),("labetalol","CONTRAINDICATIONS",2),("labetalol","WARNINGS_AND_PRECAUTIONS",2),("labetalol","DRUG_OVERVIEW",1)],
    "RR_04": [("atorvastatin","CONTRAINDICATIONS",3),("atorvastatin","HEPATIC_IMPAIRMENT",3),("atorvastatin","WARNINGS_AND_PRECAUTIONS",2),("atorvastatin","DOSAGE_AND_ADMINISTRATION",1)],
    "RR_05": [("warfarin","BOXED_WARNING",3),("warfarin","CONTRAINDICATIONS",3),("warfarin","GERIATRIC_USE",3),("warfarin","WARNINGS_AND_PRECAUTIONS",2)],
    "RR_06": [("methotrexate","BOXED_WARNING",3),("methotrexate","PREGNANCY",3),("methotrexate","CONTRAINDICATIONS",2)],
    "RR_07": [("isotretinoin","BOXED_WARNING",3),("isotretinoin","PREGNANCY",3),("isotretinoin","CONTRAINDICATIONS",2)],
    "RR_08": [("losartan","CONTRAINDICATIONS",2),("losartan","RENAL_IMPAIRMENT",2),("losartan","WARNINGS_AND_PRECAUTIONS",2),("losartan","DRUG_INTERACTIONS",1),("losartan","DOSAGE_AND_ADMINISTRATION",1)],
    "RR_09": [("hydrochlorothiazide","WARNINGS_AND_PRECAUTIONS",3),("hydrochlorothiazide","CONTRAINDICATIONS",2),("hydrochlorothiazide","DRUG_INTERACTIONS",1)],
    "RR_10": [("amlodipine","DOSAGE_AND_ADMINISTRATION",2),("amlodipine","WARNINGS_AND_PRECAUTIONS",1),("amlodipine","DRUG_OVERVIEW",1)],
    "RR_11": [("valproic_acid","BOXED_WARNING",3),("valproic_acid","PREGNANCY",3),("valproic_acid","CONTRAINDICATIONS",2)],
    "RR_12": [("nitrofurantoin","CONTRAINDICATIONS",3),("nitrofurantoin","RENAL_IMPAIRMENT",3),("nitrofurantoin","WARNINGS_AND_PRECAUTIONS",2),("nitrofurantoin","DOSAGE_AND_ADMINISTRATION",1)],
    "RR_13": [("lisinopril","CONTRAINDICATIONS",3),("lisinopril","PREGNANCY",3),("lisinopril","WARNINGS_AND_PRECAUTIONS",2)],
    "RR_14": [("rosuvastatin","CONTRAINDICATIONS",2),("rosuvastatin","WARNINGS_AND_PRECAUTIONS",2),("rosuvastatin","DRUG_OVERVIEW",1)],
    "RR_15": [("metoprolol","CONTRAINDICATIONS",2),("metoprolol","WARNINGS_AND_PRECAUTIONS",2),("metoprolol","DRUG_INTERACTIONS",1),("metoprolol","DRUG_OVERVIEW",1)],

    # ── Section B: Chat queries ────────────────────────────────────────────────
    "CH_01": [("lisinopril","CONTRAINDICATIONS",3),("lisinopril","RENAL_IMPAIRMENT",2),("lisinopril","WARNINGS_AND_PRECAUTIONS",2),("lisinopril","DOSAGE_AND_ADMINISTRATION",1)],
    "CH_02": [("metformin","DRUG_OVERVIEW",3),("metformin","DOSAGE_AND_ADMINISTRATION",1)],
    "CH_03": [("warfarin","DOSAGE_AND_ADMINISTRATION",2),("warfarin","WARNINGS_AND_PRECAUTIONS",2),("warfarin","DRUG_INTERACTIONS",2),("warfarin","BOXED_WARNING",1)],
    "CH_04": [("atorvastatin","CONTRAINDICATIONS",3),("atorvastatin","HEPATIC_IMPAIRMENT",3),("atorvastatin","WARNINGS_AND_PRECAUTIONS",2)],
    "CH_05": [("hydrochlorothiazide","WARNINGS_AND_PRECAUTIONS",2),("hydrochlorothiazide","DRUG_INTERACTIONS",2),("hydrochlorothiazide","CONTRAINDICATIONS",1)],
    "CH_06": [("labetalol","PREGNANCY",3),("methyldopa","PREGNANCY",3),("labetalol","DRUG_OVERVIEW",1),("methyldopa","DRUG_OVERVIEW",1)],
    "CH_07": [("lisinopril","DOSAGE_AND_ADMINISTRATION",3),("lisinopril","DRUG_OVERVIEW",1)],
    "CH_08": [("warfarin","DRUG_INTERACTIONS",3),("warfarin","WARNINGS_AND_PRECAUTIONS",2),("warfarin","BOXED_WARNING",1)],
    "CH_09": [("metformin","BOXED_WARNING",3),("metformin","RENAL_IMPAIRMENT",3),("metformin","DOSAGE_AND_ADMINISTRATION",2),("metformin","CONTRAINDICATIONS",2)],
    "CH_10": [("losartan","DRUG_OVERVIEW",3),("losartan","DOSAGE_AND_ADMINISTRATION",1)],
    "CH_11": [("amlodipine","GERIATRIC_USE",2),("amlodipine","WARNINGS_AND_PRECAUTIONS",2),("amlodipine","CONTRAINDICATIONS",1)],
    "CH_12": [("methotrexate","BOXED_WARNING",3),("methotrexate","CONTRAINDICATIONS",3),("methotrexate","PREGNANCY",2)],
    "CH_13": [("isotretinoin","BOXED_WARNING",3),("isotretinoin","PREGNANCY",2),("isotretinoin","CONTRAINDICATIONS",2)],
    "CH_14": [("warfarin","DRUG_INTERACTIONS",3),("warfarin","WARNINGS_AND_PRECAUTIONS",2),("ibuprofen","DRUG_INTERACTIONS",2)],
    "CH_15": [("insulin_glargine","CONTRAINDICATIONS",3),("insulin_glargine","WARNINGS_AND_PRECAUTIONS",2),("insulin_glargine","DRUG_INTERACTIONS",1)],

    # ── Section C: Overview queries ────────────────────────────────────────────
    "OV_01": [("lisinopril","DRUG_OVERVIEW",3),("lisinopril","DOSAGE_AND_ADMINISTRATION",1)],
    "OV_02": [("metformin","DRUG_OVERVIEW",3),("metformin","DOSAGE_AND_ADMINISTRATION",1)],
    "OV_03": [("atorvastatin","DRUG_OVERVIEW",3),("atorvastatin","DOSAGE_AND_ADMINISTRATION",1)],
    "OV_04": [("warfarin","DRUG_OVERVIEW",3),("warfarin","DOSAGE_AND_ADMINISTRATION",1)],
    "OV_05": [("losartan","DRUG_OVERVIEW",3),("losartan","DOSAGE_AND_ADMINISTRATION",1)],
}


# ---------------------------------------------------------------------------
# 2.  Query text (mirrors test_set.py)
# ---------------------------------------------------------------------------

QUERY_TEXT: dict[str, str] = {
    "RR_01": "Personalized risk assessment for lisinopril in a patient with renal impairment",
    "RR_02": "Personalized risk assessment for metformin in a patient with CKD",
    "RR_03": "Personalized risk assessment for labetalol in a pregnant patient with hypertension",
    "RR_04": "Personalized risk for atorvastatin in a patient with hepatic impairment",
    "RR_05": "Risk report for warfarin in an elderly patient",
    "RR_06": "Risk assessment for methotrexate in a patient planning pregnancy",
    "RR_07": "Risk report for isotretinoin in a patient with pregnancy",
    "RR_08": "Risk assessment for losartan in a patient with diabetes and renal impairment",
    "RR_09": "Risk report for hydrochlorothiazide in a patient with gout",
    "RR_10": "Risk assessment for amlodipine in a standard adult patient with hypertension",
    "RR_11": "Risk report for valproic acid in a pregnant patient",
    "RR_12": "Risk assessment for nitrofurantoin in a patient with renal impairment",
    "RR_13": "Risk report for lisinopril in a pregnant patient",
    "RR_14": "Risk assessment for rosuvastatin in a diabetic patient",
    "RR_15": "Risk report for metoprolol in a patient with heart failure",
    "CH_01": "What are the contraindications of lisinopril in patients with renal impairment?",
    "CH_02": "What is the mechanism of action of metformin?",
    "CH_03": "What monitoring is required for warfarin therapy?",
    "CH_04": "Is atorvastatin safe to use in patients with liver disease?",
    "CH_05": "What are the cardiovascular considerations for using hydrochlorothiazide?",
    "CH_06": "What antihypertensive drugs are documented as safe during pregnancy?",
    "CH_07": "What is the documented dosage range for lisinopril in hypertension?",
    "CH_08": "What are the known drug interactions of warfarin with antibiotics?",
    "CH_09": "What are the renal dosing considerations for metformin?",
    "CH_10": "What is the drug class and primary indication of losartan?",
    "CH_11": "What are the safety concerns for amlodipine in elderly patients?",
    "CH_12": "What patient populations should avoid methotrexate?",
    "CH_13": "What are the boxed warnings for isotretinoin?",
    "CH_14": "What interactions should be monitored when combining warfarin with NSAIDs?",
    "CH_15": "What are the contraindications for insulin glargine use?",
    "OV_01": "Give me an overview of lisinopril including drug class and mechanism",
    "OV_02": "What drug class does metformin belong to and what is its mechanism?",
    "OV_03": "Provide a drug overview for atorvastatin",
    "OV_04": "What is warfarin and what is it used for?",
    "OV_05": "Overview of losartan — class, mechanism, indication",
}

SECTION_IDS: dict[str, list[str]] = {
    "A": [q for q in RETRIEVAL_GROUND_TRUTH if q.startswith("RR_")],
    "B": [q for q in RETRIEVAL_GROUND_TRUTH if q.startswith("CH_")],
    "C": [q for q in RETRIEVAL_GROUND_TRUTH if q.startswith("OV_")],
}

# ---------------------------------------------------------------------------
# 3.  Metric helpers
# ---------------------------------------------------------------------------

# P0-EVAL-2 fix: SECTION_NORMALIZATION removed. Ground truth now uses the actual
# 12 fine-grained section types (BOXED_WARNING, CONTRAINDICATIONS, etc.) so no
# lossy mapping is needed. The old mapping collapsed 12 types into 4, which
# inflated metrics by treating DRUG_OVERVIEW as INTERACTIONS_AND_PHARMACOLOGY.

def _normalize_section(section: str) -> str:
    """Normalize section type for comparison — just lowercases now."""
    return (section or "").lower().strip()


def _chunk_key(chunk: "EvidenceChunk"):
    """
    Stable identity for a retrieved chunk, used to drop literal duplicates
    (e.g. the same chunk coming back from both the dense and BM25 legs of
    the hybrid retriever and surviving fusion). Prefers a real chunk/doc id
    if the model exposes one; falls back to a content-based key so two
    chunks with identical text are still treated as the same evidence even
    if the pipeline assigns them different transient ids.
    """
    for attr in ("chunk_id", "id", "doc_id"):
        val = getattr(chunk, attr, None)
        if val:
            return ("id", val)
    text = getattr(chunk, "text", None) or getattr(chunk, "content", None) or ""
    return ("content", (chunk.drug_id or "", chunk.section_type or "", text[:200]))


def dedupe_chunks(chunks: list["EvidenceChunk"]) -> tuple[list["EvidenceChunk"], int]:
    """
    Remove literal duplicate chunks while preserving rank order (first
    occurrence wins — it has the better/earlier rank). Returns
    (deduped_chunks, n_duplicates_removed) so callers can log/flag when the
    retriever is handing back repeats, which is itself a pipeline smell
    worth surfacing even though this script must not "fix" the pipeline.
    """
    seen = set()
    out = []
    for c in chunks:
        key = _chunk_key(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out, len(chunks) - len(out)


def _is_relevant(chunk: EvidenceChunk, gt: list[tuple[str, str, int]]) -> bool:
    """True if chunk (drug_id, section_type) matches any ground-truth pair."""
    cd = (chunk.drug_id or "").lower().strip()
    cs = _normalize_section(chunk.section_type)
    return any(cd == d.lower() and cs == s.lower() for d, s, _ in gt)


def _matched_gt_indices(chunks: list[EvidenceChunk], gt: list[tuple], k: int) -> set[int]:
    """
    Which *distinct* ground-truth items are represented in the top-k
    retrieved chunks, at most once each.

    This is the key correctness fix: ground truth is labelled at
    (drug_id, section_type) granularity — i.e. "old chunking" granularity,
    one label per section. The current chunking structure can split a
    single labelled section into several retrieved chunks. Recall (and any
    metric bounded by "number of relevant items found") must count each
    ground-truth item at most once no matter how many retrieved chunks map
    onto it, or the numerator can exceed the denominator and recall/NDCG
    lose their [0,1] guarantee. Earlier match wins (best rank), mirroring
    how NDCG already behaved.
    """
    used: set[int] = set()
    for c in chunks[:k]:
        if not c:
            continue
        cd = (c.drug_id or "").lower().strip()
        cs = _normalize_section(c.section_type)
        for j, (d, s, _g) in enumerate(gt):
            if j in used:
                continue
            if cd == d.lower() and cs == s.lower():
                used.add(j)
                break
    return used


def precision_at_k(chunks: list[EvidenceChunk], gt: list[tuple], k: int) -> float:
    """
    Fraction of the top-k *retrieved chunks* that are individually
    relevant. Unlike recall, this is intentionally chunk-level (not
    gt-item-level): if a genuinely relevant section was split into three
    chunks and all three appear in the top-k, all three are legitimately
    "relevant results" for the user reading the top-k list, so all three
    count. Precision is bounded by k in the denominator, so this can never
    exceed 1.0 as long as `chunks` has already been de-duplicated (see
    dedupe_chunks) — duplicate *retrieved* chunks would otherwise let the
    same evidence pad the numerator.
    """
    top = chunks[:k]
    if not top:
        return 0.0
    return sum(1 for c in top if _is_relevant(c, gt)) / k


def recall_at_k(chunks: list[EvidenceChunk], gt: list[tuple], k: int) -> float:
    """
    Fraction of *distinct ground-truth items* found in the top-k, using
    `_matched_gt_indices` so a single labelled section can't be "found"
    more than once just because it was split into multiple chunks.
    Guaranteed to be in [0,1] by construction: the numerator is
    len(a subset of gt's indices) <= len(gt) = denominator.
    """
    if not gt:
        return 1.0
    matched = _matched_gt_indices(chunks, gt, k)
    return len(matched) / len(gt)


def f1_at_k(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def mrr_score(chunks: list[EvidenceChunk], gt: list[tuple]) -> float:
    for rank, c in enumerate(chunks, 1):
        if _is_relevant(c, gt):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(chunks: list[EvidenceChunk], gt: list[tuple], k: int) -> float:
    """
    Graded NDCG@k. Uses the same `_matched_gt_indices`-style, one-gt-item-
    per-match rule as recall so the two metrics can't disagree about
    whether a section has been "found" more than once.
    """
    top = chunks[:k]
    used: set[int] = set()
    dcg = 0.0
    for i, c in enumerate(top):
        cd = (c.drug_id or "").lower().strip()
        cs = _normalize_section(c.section_type)
        for j, (d, s, g) in enumerate(gt):
            if j in used:
                continue
            if cd == d.lower() and cs == s.lower():
                dcg += (2 ** g - 1) / math.log2(i + 2)
                used.add(j)
                break
    ideal = sorted([g for _, _, g in gt], reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    val = dcg / idcg if idcg > 0 else 0.0
    # Defensive: graded NDCG is mathematically bounded by [0,1] as long as
    # `chunks` contains no literal duplicates and dcg/idcg use the same
    # gain function — assert instead of silently returning a bad number.
    assert -1e-9 <= val <= 1 + 1e-9, f"NDCG@{k} out of bounds: {val}"
    return max(0.0, min(1.0, val))


def hit_rate_at_k(chunks: list[EvidenceChunk], gt: list[tuple], k: int) -> float:
    return float(any(_is_relevant(c, gt) for c in chunks[:k]))


def first_relevant_rank(chunks: list[EvidenceChunk], gt: list[tuple]) -> Optional[float]:
    for rank, c in enumerate(chunks, 1):
        if _is_relevant(c, gt):
            return float(rank)
    return None


# ---------------------------------------------------------------------------
# 4.  Per-query evaluation
# ---------------------------------------------------------------------------

def evaluate_one(
    query_id: str,
    query: str,
    gt: list[tuple[str, str, int]],
    retriever: HybridRetriever,
    k_values: list[int],
) -> dict:
    max_k = max(k_values)
    t0 = time.perf_counter()

    # ------------------------------------------------------------------
    # BUG FIX — data leakage:
    # The previous version derived `metadata_filter` from the *ground
    # truth* drug(s) for this query and handed it straight to the
    # retriever ({"drug_id": {"$eq"/"$in": ...}}). That means retrieval
    # was told the correct answer before it ever ran — it only had to
    # search inside the already-correct drug's chunks. That is not what
    # happens for a real user query, and it inflates every retrieval
    # metric (precision, recall, NDCG, MRR, hit rate) because the hardest
    # part of retrieval (finding the right drug at all) was being done by
    # the ground truth instead of the pipeline. Real users don't attach a
    # drug_id filter to their question — the retriever has to earn it.
    # Evaluation must exercise retrieval exactly as a real query would, so
    # no metadata filter is derived from `gt` here.
    # ------------------------------------------------------------------
    metadata_filter = None

    try:
        chunks = retriever.retrieve(
            query=query,
            k=max_k,
            metadata_filter=metadata_filter,
            dense_k=max(30, max_k * 3),
            bm25_k=max(30, max_k * 3),
        )
    except Exception as exc:
        logger.error("retrieval_error", qid=query_id, error=str(exc))
        chunks = []
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    # BUG FIX — duplicate retrieved chunks: if the hybrid fusion (dense +
    # BM25 + reranker) returns the same underlying chunk more than once,
    # it must not be allowed to occupy two ranks and get double-counted by
    # precision/hit-rate. De-duplicate before any metric touches `chunks`.
    chunks, n_duplicates = dedupe_chunks(chunks)
    if n_duplicates:
        logger.warning("duplicate_chunks_removed", qid=query_id, n=n_duplicates)

    row: dict = {
        "query_id":    query_id,
        "query":       query[:90],
        "n_retrieved": len(chunks),
        "n_relevant":  len(gt),
        "n_duplicate_chunks_removed": n_duplicates,
        "latency_ms":  latency_ms,
        "mrr":         round(mrr_score(chunks, gt), 4),
        "avg_rank":    first_relevant_rank(chunks, gt),
        "chunks_preview": [
            {
                "rank":     i + 1,
                "drug":     c.drug_id or "",
                "section":  c.section_type or "",
                "score":    round(c.score, 4),
                "relevant": _is_relevant(c, gt),
            }
            for i, c in enumerate(chunks[:12])
        ],
    }

    for k in k_values:
        p = precision_at_k(chunks, gt, k)
        r = recall_at_k(chunks, gt, k)
        row[f"precision@{k}"] = round(p, 4)
        row[f"recall@{k}"]    = round(r, 4)
        row[f"f1@{k}"]        = round(f1_at_k(p, r), 4)
        row[f"ndcg@{k}"]      = round(ndcg_at_k(chunks, gt, k), 4)
        row[f"hit_rate@{k}"]  = round(hit_rate_at_k(chunks, gt, k), 4)

    return row


# ---------------------------------------------------------------------------
# 5.  Aggregation
# ---------------------------------------------------------------------------

def aggregate(rows: list[dict], k_values: list[int]) -> dict:
    def avg(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 4) if v else None

    agg: dict = {"n_queries": len(rows)}
    agg["mrr"] = avg([r["mrr"] for r in rows])

    # NOTE: avg_rank is computed over queries that had at least one relevant
    # hit (first_relevant_rank is None for a total miss and is excluded by
    # `avg`). That is standard for "average rank of the first relevant
    # result", but it means avg_rank alone can look good even if many
    # queries never found anything — it must always be read next to
    # hit_rate@k / recall, never in isolation. Renamed here for clarity.
    agg["avg_rank_of_hits"] = avg([r["avg_rank"] for r in rows])
    agg["avg_rank"] = agg["avg_rank_of_hits"]  # kept for backward compatibility

    for k in k_values:
        for m in ("precision", "recall", "f1", "ndcg", "hit_rate"):
            agg[f"{m}@{k}"] = avg([r[f"{m}@{k}"] for r in rows])

    # Defensive sanity checks — these metrics are mathematically guaranteed
    # to be within [0,1]; if they ever aren't, something upstream (ground
    # truth, chunk identity, or a future edit to these functions) broke the
    # invariant and that must fail loudly rather than silently ship a bad
    # number in a report.
    for k in k_values:
        for m in ("precision", "recall", "f1", "ndcg", "hit_rate"):
            v = agg[f"{m}@{k}"]
            if v is not None:
                assert -1e-9 <= v <= 1 + 1e-9, f"{m}@{k} out of [0,1]: {v}"
    if agg["mrr"] is not None:
        assert -1e-9 <= agg["mrr"] <= 1 + 1e-9, f"MRR out of [0,1]: {agg['mrr']}"

    # Comparability metadata: any future comparison between two eval runs
    # (e.g. an older 35-query run vs a newer 15-query run) is only valid if
    # the same query set was used. Persist the exact ids/count so that
    # comparison can be checked mechanically instead of assumed.
    agg["query_ids"] = sorted(r["query_id"] for r in rows)
    agg["n_duplicate_chunks_removed_total"] = sum(
        r.get("n_duplicate_chunks_removed", 0) for r in rows
    )
    return agg


def assert_comparable(agg_a: dict, agg_b: dict) -> None:
    """
    Guard against comparing two eval runs that don't cover the same query
    set (e.g. an older 35-query run vs a trimmed 15-query run). Aggregate
    metrics from different query sets are not comparable — different
    queries have different intrinsic difficulty, so a rise or fall in the
    aggregate can simply reflect which queries were included, not a real
    change in retrieval quality. Raises if the two runs disagree.
    """
    ids_a, ids_b = set(agg_a.get("query_ids", [])), set(agg_b.get("query_ids", []))
    if ids_a != ids_b:
        only_a = ids_a - ids_b
        only_b = ids_b - ids_a
        raise ValueError(
            "Eval runs are not comparable — different query sets.\n"
            f"  Run A: {len(ids_a)} queries, Run B: {len(ids_b)} queries.\n"
            f"  Only in A: {sorted(only_a) or '-'}\n"
            f"  Only in B: {sorted(only_b) or '-'}\n"
            "Re-run both against the same --section/query set before "
            "comparing aggregate numbers."
        )


# ---------------------------------------------------------------------------
# 6.  Console output
# ---------------------------------------------------------------------------

def print_table(rows: list[dict], agg: dict, ks: list[int]) -> None:
    hdr = ["Query ID", "MRR", "AvgRnk"] + [f"P@{k}" for k in ks] + [f"HR@{k}" for k in ks] + [f"NDCG@{k}" for k in ks]
    widths = [12] + [7] * (len(hdr) - 1)
    sep = "  ".join("-" * w for w in widths)

    def fmt_row(vals):
        return "  ".join(str(v).ljust(w) for v, w in zip(vals, widths))

    print(f"\n{'=' * 72}")
    print("  MEDRESOLVE AI — Retrieval Metrics")
    print(f"{'=' * 72}")
    print("  " + fmt_row(hdr))
    print("  " + sep)

    for row in rows:
        ar = row["avg_rank"]
        vals = [row["query_id"], f"{row['mrr']:.3f}", str(ar or "N/A")]
        for k in ks:
            vals.append(f"{row[f'precision@{k}']:.3f}")
        for k in ks:
            vals.append(f"{row[f'hit_rate@{k}']:.3f}")
        for k in ks:
            vals.append(f"{row[f'ndcg@{k}']:.3f}")
        print("  " + fmt_row(vals))

    print("  " + sep)
    ar = agg.get("avg_rank")
    agg_vals = ["AGGREGATE", f"{agg['mrr']:.3f}", f"{ar:.1f}" if ar else "N/A"]
    for k in ks:
        agg_vals.append(f"{agg[f'precision@{k}']:.3f}")
    for k in ks:
        agg_vals.append(f"{agg[f'hit_rate@{k}']:.3f}")
    for k in ks:
        agg_vals.append(f"{agg[f'ndcg@{k}']:.3f}")
    print("  " + fmt_row(agg_vals))
    print(f"{'=' * 72}")


# ---------------------------------------------------------------------------
# 7.  HTML report
# ---------------------------------------------------------------------------

def _color(v: float, hi=0.75, lo=0.5) -> str:
    return "#22c55e" if v >= hi else "#f59e0b" if v >= lo else "#ef4444"


def save_html(rows: list[dict], agg: dict, ks: list[int], path: Path) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = (["Query", "MRR", "AvgRank"]
            + [f"P@{k}" for k in ks]
            + [f"R@{k}" for k in ks]
            + [f"F1@{k}" for k in ks]
            + [f"NDCG@{k}" for k in ks]
            + [f"HR@{k}" for k in ks]
            + ["ms"])

    hdr_html = "".join(f"<th>{c}</th>" for c in cols)

    def row_html(r: dict) -> str:
        qid = r["query_id"]
        ar  = r["avg_rank"]
        mrr_color = _color(r["mrr"])
        cells = (
            f"<td title='{r['query']}'>{qid}</td>"
            f"<td style='color:{mrr_color}'>{r['mrr']:.3f}</td>"
            f"<td>{int(ar) if ar else chr(8211)}</td>"
        )
        for k in ks:
            v = r[f"precision@{k}"]; cells += f"<td style='color:{_color(v)}'>{v:.3f}</td>"
        for k in ks:
            v = r[f"recall@{k}"]; cells += f"<td style='color:{_color(v)}'>{v:.3f}</td>"
        for k in ks:
            v = r[f"f1@{k}"]; cells += f"<td style='color:{_color(v)}'>{v:.3f}</td>"
        for k in ks:
            v = r[f"ndcg@{k}"]; cells += f"<td style='color:{_color(v)}'>{v:.3f}</td>"
        for k in ks:
            v = r[f"hit_rate@{k}"]; cells += f"<td style='color:{_color(v)}'>{v:.3f}</td>"
        cells += f"<td>{r['latency_ms']:.0f}</td>"

        # chunk preview
        def _chunk_row(c: dict) -> str:
            bg = '#143d21' if c['relevant'] else '#3d1414'
            rel_sym = '\u2713' if c['relevant'] else '\u2717'
            return (
                f"<tr style='background:{bg}'>"
                f"<td>#{c['rank']}</td><td>{c['drug']}</td>"
                f"<td>{c['section']}</td><td>{c['score']:.4f}</td>"
                f"<td>{rel_sym}</td></tr>"
            )
        preview_rows = "".join(_chunk_row(c) for c in r["chunks_preview"])
        detail = (
            f"<tr id='d-{qid}' style='display:none'>"
            "<td colspan='99' style='padding:0.5rem 2rem;background:#0a0f1c'>"
            "<table style='font-size:0.75rem;border-collapse:collapse'>"
            "<tr><th>#</th><th>Drug</th><th>Section</th><th>Score</th><th>Rel</th></tr>"
            + preview_rows + "</table></td></tr>"
        )
        return (
            f"<tr onclick=\"t('{qid}')\" style='cursor:pointer'>{cells}</tr>"
            + detail
        )

    def agg_html() -> str:
        ar = agg.get("avg_rank")
        agg_mrr_color = _color(agg["mrr"])
        agg_mrr_val   = agg["mrr"]
        ar_str = f"{ar:.1f}" if ar else chr(8211)
        cells = (
            "<td><b>AGGREGATE</b></td>"
            f"<td style='color:{agg_mrr_color}'><b>{agg_mrr_val:.3f}</b></td>"
            f"<td><b>{ar_str}</b></td>"
        )
        for k in ks:
            v = agg[f"precision@{k}"]; cells += f"<td style='color:{_color(v)}'><b>{v:.3f}</b></td>"
        for k in ks:
            v = agg[f"recall@{k}"]; cells += f"<td style='color:{_color(v)}'><b>{v:.3f}</b></td>"
        for k in ks:
            v = agg[f"f1@{k}"]; cells += f"<td style='color:{_color(v)}'><b>{v:.3f}</b></td>"
        for k in ks:
            v = agg[f"ndcg@{k}"]; cells += f"<td style='color:{_color(v)}'><b>{v:.3f}</b></td>"
        for k in ks:
            v = agg[f"hit_rate@{k}"]; cells += f"<td style='color:{_color(v)}'><b>{v:.3f}</b></td>"
        cells += "<td>–</td>"
        return f"<tr style='background:#060c18'>{cells}</tr>"

    k0, kn = ks[0], ks[-1]
    kpis = [
        ("MRR",            agg["mrr"]),
        (f"Precision@{k0}", agg[f"precision@{k0}"]),
        (f"Precision@{kn}", agg[f"precision@{kn}"]),
        (f"Recall@{kn}",    agg[f"recall@{kn}"]),
        (f"F1@{kn}",        agg[f"f1@{kn}"]),
        (f"NDCG@{kn}",      agg[f"ndcg@{kn}"]),
        (f"Hit Rate@{kn}",  agg[f"hit_rate@{kn}"]),
    ]
    kpi_html = "".join(
        f"<div class='kpi'><div class='kl'>{label}</div>"
        f"<div class='kv' style='color:{_color(v)}'>{v:.3f}</div></div>"
        for label, v in kpis
    )

    body_html = "".join(row_html(r) for r in rows) + agg_html()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>MedResolve RAG Eval</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0b1120;color:#e2e8f0;font:13px/1.5 system-ui,sans-serif;padding:2rem}}
h1{{font-size:1.5rem;color:#818cf8;margin-bottom:.25rem}}
.sub{{color:#64748b;font-size:.8rem;margin-bottom:1.5rem}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:.8rem;margin-bottom:1.5rem}}
.kpi{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:.8rem 1rem}}
.kl{{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin-bottom:.3rem}}
.kv{{font-size:1.5rem;font-weight:800}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:1rem;overflow:auto}}
table{{width:100%;border-collapse:collapse}}
th{{background:#0b1120;padding:.5rem .4rem;text-align:left;white-space:nowrap;color:#64748b;
    font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid #334155}}
td{{padding:.4rem .4rem;border-bottom:1px solid #1e293b;white-space:nowrap}}
tr:hover td{{background:#25334a}}
</style>
</head>
<body>
<h1>🏥 MedResolve AI — RAG Retrieval Evaluation</h1>
<p class="sub">Generated {ts} &nbsp;|&nbsp; {len(rows)} queries &nbsp;|&nbsp; k={ks}</p>
<div class="kpis">{kpi_html}</div>
<div class="card">
  <p style="color:#64748b;font-size:.75rem;margin-bottom:.6rem">Click a row to see the top-12 retrieved chunks.</p>
  <table><thead><tr>{hdr_html}</tr></thead><tbody>{body_html}</tbody></table>
</div>
<script>function t(id){{var r=document.getElementById('d-'+id);r.style.display=r.style.display==='none'?'table-row':'none';}}</script>
</body></html>"""

    path.write_text(html, encoding="utf-8")
    print(f"\n  HTML report: {path}")


# ---------------------------------------------------------------------------
# 8.  CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="MedResolve RAG Retrieval Evaluation")
    parser.add_argument("--k", nargs="+", type=int, default=[1, 3, 5, 10],
                        help="k values (default: 1 3 5 10)")
    parser.add_argument("--section", choices=["A", "B", "C", "all"], default="all",
                        help="A=RiskReport B=Chat C=Overview all=everything")
    parser.add_argument("--save-html", action="store_true",
                        help="Save interactive HTML report")
    args = parser.parse_args()

    query_ids = (
        list(RETRIEVAL_GROUND_TRUTH.keys())
        if args.section == "all"
        else SECTION_IDS[args.section]
    )
    ks = sorted(set(args.k))

    print(f"\n{'=' * 60}")
    print(f"  MEDRESOLVE AI — RAG Evaluation")
    print(f"  Queries: {len(query_ids)}  |  k = {ks}")
    print(f"{'=' * 60}")
    print("  Loading retriever (embedding + BM25 + reranker)...")

    retriever = build_retriever(source="drugs")
    rows: list[dict] = []

    for i, qid in enumerate(query_ids, 1):
        query = QUERY_TEXT[qid]
        gt    = RETRIEVAL_GROUND_TRUTH[qid]
        print(f"\n  [{i:02d}/{len(query_ids)}] {qid}: {query[:62]}...")

        row = evaluate_one(qid, query, gt, retriever, ks)
        rows.append(row)

        p1  = row.get("precision@1",  0.0)
        hr5 = row.get("hit_rate@5",   0.0)
        nd5 = row.get("ndcg@5",       0.0)
        sym = "[HIT]" if hr5 > 0 else "[---]"
        print(f"     {sym}  MRR={row['mrr']:.3f}  P@1={p1:.3f}  "
              f"HR@5={hr5:.3f}  NDCG@5={nd5:.3f}  [{row['latency_ms']:.0f}ms]")

        # Show top-3 chunks inline
        for c in row["chunks_preview"][:3]:
            rel_mark = "REL" if c["relevant"] else "   "
            print(f"       [{rel_mark}] #{c['rank']} {c['drug']}/{c['section']}  score={c['score']:.4f}")

    agg = aggregate(rows, ks)
    print_table(rows, agg, ks)

    # Save JSON (always)
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"rag_eval_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"aggregate": agg, "rows": rows}, f, indent=2, default=str)
    print(f"\n  JSON saved: {json_path}")

    if args.save_html:
        save_html(rows, agg, ks, out_dir / f"rag_eval_{ts}.html")

    # Summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Queries   : {agg['n_queries']}  (ids: {', '.join(agg['query_ids'])})")
    print(f"  MRR       : {agg['mrr']:.4f}")
    ar = agg['avg_rank']
    print(f"  Avg rank  : {f'{ar:.2f}' if ar else 'N/A'}  (hits only — read together with Hit Rate, not alone)")
    dup = agg.get("n_duplicate_chunks_removed_total", 0)
    if dup:
        print(f"  [!] {dup} duplicate retrieved chunk(s) removed before scoring — investigate retriever fusion/dedup.")
    print("  NOTE: aggregate metrics above are only comparable to another run")
    print("        that used this exact query-id set. See assert_comparable().")
    for k in ks:
        p  = agg[f'precision@{k}']
        r  = agg[f'recall@{k}']
        f1 = agg[f'f1@{k}']
        nd = agg[f'ndcg@{k}']
        hr = agg[f'hit_rate@{k}']
        badge = "[***]" if p >= 0.75 else ("[!] " if p >= 0.5 else "[X] ")
        print(f"  k={k:2d}  P={p:.3f}  R={r:.3f}  F1={f1:.3f}  NDCG={nd:.3f}  HR={hr:.3f}  {badge}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
