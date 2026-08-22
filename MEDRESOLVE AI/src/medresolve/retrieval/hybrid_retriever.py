"""
MEDRESOLVE AI — Hybrid Medical Retriever
Combines dense vector search + BM25 lexical retrieval + cross-encoder reranking.
Drug-only system — guideline retriever branch removed.

Key fixes vs original:
- Removed wrong BGE query prefix (model is all-MiniLM-L6-v2, no prefix needed)
- Added cross-encoder score threshold filtering
- Batched BM25 metadata fetch (single collection.get instead of N calls)
- Medical-aware BM25 tokenization (strips punctuation, handles abbreviations)
- Exposes cross-encoder scores (not RRF) in EvidenceChunk.score
- Fixed $and filter support in _check_metadata_filter
"""

from __future__ import annotations
import pickle
import re
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
import numpy as np
import structlog

from medresolve.config import get_settings
from medresolve.models import EvidenceChunk, SourceType
# P0-CHUNK-1 fix: single canonical BM25 tokenizer shared between ingestion and retrieval.
# Previously this file had its own _tokenize_medical() copy — any drift between the two
# would silently corrupt BM25 scoring because index tokens ≠ query tokens.
from medresolve.ingestion.drug_normalizer import _tokenize_bm25 as _tokenize_medical

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """
    Hybrid retriever combining:
    1. Dense vector search (sentence-transformers via ChromaDB)
    2. BM25 lexical retrieval (for exact medical term matching)
    3. Reciprocal Rank Fusion (RRF) for merging results
    4. Cross-encoder reranking with score threshold filtering
    """

    _embedding_model: Optional[SentenceTransformer] = None
    _reranker: Optional[CrossEncoder] = None

    def __init__(
        self,
        collection: chromadb.Collection,
        bm25_index_path: Path,
        source_type: SourceType,
    ):
        self.collection = collection
        self.bm25_index_path = bm25_index_path
        self.source_type = source_type
        self.settings = get_settings()
        self._bm25_data: Optional[dict] = None

    @classmethod
    def get_embedding_model(cls) -> SentenceTransformer:
        """Singleton embedding model."""
        if cls._embedding_model is None:
            settings = get_settings()
            logger.info("loading_embedding_model", model=settings.embedding_model)
            cls._embedding_model = SentenceTransformer(
                settings.embedding_model,
                device=settings.embedding_device,
            )
        return cls._embedding_model

    @classmethod
    def get_reranker(cls) -> CrossEncoder:
        """Singleton reranker model."""
        if cls._reranker is None:
            settings = get_settings()
            logger.info("loading_reranker", model=settings.reranker_model)
            cls._reranker = CrossEncoder(settings.reranker_model)
        return cls._reranker

    def retrieve(
        self,
        query: str,
        k: int = 8,
        metadata_filter: Optional[dict] = None,
        dense_k: Optional[int] = None,
        bm25_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> list[EvidenceChunk]:
        """
        Main retrieval method using hybrid search + reranking.

        Args:
            query: User query or sub-query
            k: Final number of results after reranking
            metadata_filter: ChromaDB metadata filter dict
            dense_k: Candidates from dense search (default from config)
            bm25_k: Candidates from BM25 search (default from config)
            score_threshold: Min cross-encoder score to keep chunk (None → use settings default)

        Returns:
            List of EvidenceChunk sorted by cross-encoder score (best first),
            filtered by score_threshold.
        """
        # P1-E: defaults now come from settings so operators can tune via config
        if dense_k is None:
            dense_k = self.settings.retrieval_dense_k
        if bm25_k is None:
            bm25_k = self.settings.retrieval_bm25_k

        threshold = score_threshold if score_threshold is not None else self.settings.reranker_score_threshold

        # 1. Dense retrieval
        dense_results = self._dense_retrieve(query, dense_k, metadata_filter)

        # 2. BM25 retrieval
        bm25_results = self._bm25_retrieve(query, bm25_k, metadata_filter)

        # 3. RRF fusion
        fused = self._reciprocal_rank_fusion(
            [dense_results, bm25_results],
            k=dense_k + bm25_k,
        )

        if not fused:
            return []

        # 4. Cross-encoder reranking with score threshold
        reranked = self._rerank(query, fused, top_k=k, score_threshold=threshold)

        logger.debug(
            "retrieve_complete",
            query=query[:60],
            dense_candidates=len(dense_results),
            bm25_candidates=len(bm25_results),
            fused=len(fused),
            returned=len(reranked),
        )

        return reranked

    def _dense_retrieve(
        self,
        query: str,
        k: int,
        metadata_filter: Optional[dict],
    ) -> list[tuple[str, float, dict, str]]:
        """Dense vector retrieval from ChromaDB. Returns (id, score, metadata, document) tuples."""
        model = self.get_embedding_model()

        # NOTE: all-MiniLM-L6-v2 does NOT use BGE-style query prefixes.
        # Removed the wrong "Represent this sentence for searching..." prefix.
        query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()

        where_clause = metadata_filter if metadata_filter else None

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, max(1, self.collection.count())),
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error("dense_retrieve_failed", error=str(e))
            return []

        if not results or not results["ids"]:
            return []

        output = []
        for doc_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity score
            score = 1.0 - dist
            output.append((doc_id, score, meta, doc))

        return output

    def _bm25_retrieve(
        self,
        query: str,
        k: int,
        metadata_filter: Optional[dict],
    ) -> list[tuple[str, float, dict, str]]:
        """BM25 lexical retrieval with medical-aware tokenization and batched metadata fetch."""
        bm25_data = self._load_bm25()
        if not bm25_data:
            return []

        bm25: BM25Okapi = bm25_data["bm25"]
        ids: list[str] = bm25_data["ids"]
        documents: list[str] = bm25_data["documents"]

        # Medical-aware tokenization (same as used during index build)
        tokenized_query = _tokenize_medical(query)
        if not tokenized_query:
            return []

        scores = bm25.get_scores(tokenized_query)

        # P0-RET-1 fix: Do NOT slice to [:k] before metadata filtering.
        # Previously, positive_indices[:k] was applied first, then metadata_filter
        # discarded non-matching entries — leaving fewer than k results.
        # Now: keep all positive-score candidates, fetch metadata, filter, THEN slice.
        top_indices = np.argsort(scores)[::-1][:k * 10]  # Large pool for filtering
        positive_indices = [i for i in top_indices if scores[i] > 0]

        if not positive_indices:
            return []

        # Batch-fetch metadata for all positive candidates at once
        candidate_ids = [ids[i] for i in positive_indices]
        candidate_scores = [scores[i] for i in positive_indices]
        candidate_docs = [documents[i] for i in positive_indices]

        # ── Batch metadata fetch (single call instead of N individual calls) ──
        try:
            batch_result = self.collection.get(
                ids=candidate_ids,
                include=["metadatas", "documents"],
            )
            id_to_meta: dict[str, dict] = {}
            id_to_doc: dict[str, str] = {}
            for doc_id, meta, doc in zip(
                batch_result.get("ids", []),
                batch_result.get("metadatas", []),
                batch_result.get("documents", []),
            ):
                id_to_meta[doc_id] = meta
                id_to_doc[doc_id] = doc
        except Exception as e:
            logger.warning("bm25_batch_fetch_failed", error=str(e))
            id_to_meta = {}
            id_to_doc = {}

        # Apply metadata filter FIRST, then take top k
        output = []
        for doc_id, raw_score, fallback_doc in zip(candidate_ids, candidate_scores, candidate_docs):
            meta = id_to_meta.get(doc_id, {})
            doc = id_to_doc.get(doc_id, fallback_doc)

            # Apply metadata filter BEFORE [:k] — this is the P0-RET-1 fix
            if metadata_filter and not self._check_metadata_filter(meta, metadata_filter):
                continue

            # Normalize BM25 score to 0-1.
            # NOTE (P3-A): This normalization is cosmetic — RRF uses rank positions
            # (1/(k+rank+1)), not score values, so this does NOT affect fusion ranking.
            # The cross-encoder score in _rerank() overwrites this downstream.
            # Kept for debugging/logging purposes only.
            norm_score = min(raw_score / 20.0, 1.0)
            output.append((doc_id, norm_score, meta, doc))

            if len(output) >= k:
                break

        return output

    def _reciprocal_rank_fusion(
        self,
        result_lists: list[list[tuple[str, float, dict, str]]],
        k: int = 60,
    ) -> list[tuple[str, float, dict, str]]:
        """Merge multiple ranked lists using Reciprocal Rank Fusion (RRF)."""
        rrf_scores: dict[str, float] = {}
        doc_data: dict[str, tuple[dict, str]] = {}

        for results in result_lists:
            for rank, (doc_id, score, meta, doc) in enumerate(results):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
                doc_data[doc_id] = (meta, doc)

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        return [
            (doc_id, rrf_scores[doc_id], doc_data[doc_id][0], doc_data[doc_id][1])
            for doc_id in sorted_ids
        ]

    def _rerank(
        self,
        query: str,
        candidates: list[tuple[str, float, dict, str]],
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[EvidenceChunk]:
        """Cross-encoder reranking with score threshold filtering."""
        if not candidates:
            return []

        reranker = self.get_reranker()
        pairs = [(query, doc) for _, _, _, doc in candidates]

        try:
            scores = reranker.predict(pairs)
        except Exception as e:
            logger.error("reranking_failed", error=str(e))
            # Fallback: use RRF scores
            scores = [score for _, score, _, _ in candidates]

        scored = list(zip(scores, candidates))
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        filtered_count = 0
        for rerank_score, (doc_id, rrf_score, meta, doc) in scored[:top_k * 2]:
            # Apply score threshold strictly (P1-D fix: removed forced min-1-result guard).
            # Previously: `if len(results) >= 1: continue` forced the first candidate through
            # regardless of its score. This undermines the threshold concept and can push
            # irrelevant chunks into evidence. Let callers handle empty results via re-retrieval.
            if float(rerank_score) < score_threshold:
                filtered_count += 1
                logger.debug(
                    "chunk_filtered_by_threshold",
                    chunk_id=doc_id,
                    score=round(float(rerank_score), 3),
                    threshold=score_threshold,
                )
                continue

            chunk = self._meta_to_evidence_chunk(doc_id, doc, meta, float(rerank_score))
            if chunk:
                results.append(chunk)
                if len(results) >= top_k:
                    break

        if filtered_count > 0:
            logger.info("chunks_filtered_by_threshold", count=filtered_count, threshold=score_threshold)

        return results

    def _meta_to_evidence_chunk(
        self,
        doc_id: str,
        doc: str,
        meta: dict,
        score: float,
    ) -> Optional[EvidenceChunk]:
        """Convert ChromaDB metadata to EvidenceChunk (drug evidence only)."""
        import json as _json

        tpf_raw = meta.get("target_patient_factors", "[]")
        try:
            target_factors = _json.loads(tpf_raw) if isinstance(tpf_raw, str) else tpf_raw
        except Exception:
            target_factors = []

        return EvidenceChunk(
            chunk_id=doc_id,
            source_type=SourceType.DRUG_EVIDENCE,
            content=doc,
            score=score,  # Cross-encoder score (not RRF score)
            drug_name=meta.get("drug_name"),
            drug_id=meta.get("drug_id"),
            section_type=meta.get("section_type"),
            target_patient_factors=target_factors,
            category=meta.get("category"),
            has_boxed_warning=bool(meta.get("has_boxed_warning", False)),
            has_contraindications=bool(meta.get("has_contraindications", False)),
            primary_indication=meta.get("primary_indication"),
        )

    def _load_bm25(self) -> Optional[dict]:
        """Load BM25 index from disk (cached)."""
        if self._bm25_data is not None:
            return self._bm25_data

        if not self.bm25_index_path.exists():
            logger.warning("bm25_index_not_found", path=str(self.bm25_index_path))
            return None

        with open(self.bm25_index_path, "rb") as f:
            self._bm25_data = pickle.load(f)

        return self._bm25_data

    def _check_metadata_filter(self, meta: dict, filter_dict: dict) -> bool:
        """
        Check if metadata matches a ChromaDB-style filter dict.
        Supports: $eq, $in, $contains, $and, $or operators.
        """
        if not filter_dict:
            return True

        # Handle $and operator
        if "$and" in filter_dict:
            return all(self._check_metadata_filter(meta, sub) for sub in filter_dict["$and"])

        # Handle $or operator
        if "$or" in filter_dict:
            return any(self._check_metadata_filter(meta, sub) for sub in filter_dict["$or"])

        for key, value in filter_dict.items():
            if key.startswith("$"):
                continue  # Skip top-level operators already handled
            if isinstance(value, dict):
                for op, op_val in value.items():
                    meta_val = meta.get(key)
                    if op == "$eq" and meta_val != op_val:
                        return False
                    elif op == "$ne" and meta_val == op_val:
                        return False
                    elif op == "$in" and meta_val not in op_val:
                        return False
                    elif op == "$nin" and meta_val in op_val:
                        return False
                    elif op == "$contains" and op_val not in str(meta_val):
                        return False
            else:
                if meta.get(key) != value:
                    return False
        return True


def build_retriever(source: str = "drugs") -> HybridRetriever:
    """
    Factory function to build a HybridRetriever for the drug knowledge base.
    Only 'drugs' is supported — guideline retriever has been removed.
    """
    settings = get_settings()

    client = chromadb.PersistentClient(
        path=str(settings.chroma_persist_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    collection = client.get_or_create_collection(
        name=settings.chroma_drug_collection,
        metadata={"hnsw:space": "cosine"},
    )
    bm25_path = settings.bm25_index_dir / "drugs_bm25.pkl"
    return HybridRetriever(collection, bm25_path, SourceType.DRUG_EVIDENCE)
