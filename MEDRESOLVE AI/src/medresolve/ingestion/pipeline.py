"""
MEDRESOLVE AI — Main Ingestion Pipeline
Orchestrates drug normalization, vector indexing, and BM25 building.
Run this once to build the knowledge base: python scripts/ingest.py
Guideline ingestion removed — drug-only system.
"""

from __future__ import annotations
import json
import pickle
import time
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
import structlog
from tqdm import tqdm

from medresolve.config import get_settings
from medresolve.ingestion.drug_normalizer import DrugNormalizer, DrugChunk, _tokenize_bm25

logger = structlog.get_logger(__name__)


class MedResolveIngestionPipeline:
    """
    Drug-only ingestion pipeline for MEDRESOLVE AI.
    Builds ChromaDB collection and BM25 index from drug knowledge base data.
    """

    def __init__(self):
        self.settings = get_settings()
        self.embedding_model: SentenceTransformer | None = None
        self._chroma_client: chromadb.PersistentClient | None = None

    def _get_client(self) -> chromadb.PersistentClient:
        """Return the single ChromaDB client (lazy-init)."""
        if self._chroma_client is None:
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.settings.chroma_persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._chroma_client

    def _get_collection(self, name: str) -> chromadb.Collection:
        """
        Always fetch a fresh collection reference from the persistent client.
        Avoids the ChromaDB Rust-backend stale-reference bug.
        """
        client = self._get_client()
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def run(self, force_rebuild: bool = False) -> dict[str, Any]:
        """
        Run the drug ingestion pipeline.

        Args:
            force_rebuild: If True, drop existing collection and rebuild.

        Returns:
            Summary statistics dict.
        """
        start = time.time()
        logger.info("ingestion_pipeline_start", force_rebuild=force_rebuild)

        self.settings.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.settings.bm25_index_dir.mkdir(parents=True, exist_ok=True)

        # Load embedding model
        logger.info("loading_embedding_model", model=self.settings.embedding_model)
        self.embedding_model = SentenceTransformer(
            self.settings.embedding_model,
            device=self.settings.embedding_device,
        )
        logger.info("embedding_model_loaded")

        # Optionally drop & recreate collection
        if force_rebuild:
            self._drop_collection()

        # ── Drug Ingestion ────────────────────────────────────────────────────
        logger.info("starting_drug_ingestion")
        normalizer = DrugNormalizer(self.settings.drug_kb_dir)
        drug_chunks = normalizer.load_all_chunks()

        drug_stats = self._index_drug_chunks(
            self.settings.chroma_drug_collection,
            drug_chunks,
            force_rebuild,
        )
        if drug_chunks:
            self._build_bm25_index(
                chunks=[c.content for c in drug_chunks],
                ids=[c.chunk_id for c in drug_chunks],
                index_name="drugs",
            )

        elapsed = time.time() - start
        summary = {
            "elapsed_seconds": round(elapsed, 1),
            "drug_chunks_indexed": drug_stats["chunks_indexed"],
            "total_chunks": drug_stats["chunks_indexed"],
        }
        # Log per-drug chunk distribution
        drug_dist: dict[str, int] = {}
        for c in drug_chunks:
            drug_dist[c.drug_id] = drug_dist.get(c.drug_id, 0) + 1
        logger.info(
            "drug_chunk_distribution",
            total_drugs=len(drug_dist),
            total_chunks=len(drug_chunks),
            avg_per_drug=round(len(drug_chunks) / max(len(drug_dist), 1), 1),
            distribution=dict(sorted(drug_dist.items(), key=lambda x: x[1], reverse=True)),
        )

        logger.info("ingestion_complete", **summary)
        return summary

    def _drop_collection(self) -> None:
        """Drop existing drug collection for a force rebuild."""
        client = self._get_client()
        try:
            client.delete_collection(self.settings.chroma_drug_collection)
            logger.info("collection_deleted", name=self.settings.chroma_drug_collection)
        except Exception:
            pass

    def _embed_texts(self, texts: list[str], desc: str = "Embedding") -> list[list[float]]:
        """Embed a list of texts in batches."""
        assert self.embedding_model is not None
        all_embeddings: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size

        for i in tqdm(range(0, len(texts), batch_size), desc=desc):
            batch = texts[i : i + batch_size]
            embeddings = self.embedding_model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            all_embeddings.extend(embeddings.tolist())

        return all_embeddings

    def _index_drug_chunks(
        self,
        collection_name: str,
        chunks: list[DrugChunk],
        force_rebuild: bool,
    ) -> dict:
        """Embed and index drug chunks into ChromaDB."""
        if not chunks:
            return {"chunks_indexed": 0}

        collection = self._get_collection(collection_name)
        existing_count = collection.count()
        if existing_count > 0 and not force_rebuild:
            logger.info("drug_collection_exists", count=existing_count)
            return {"chunks_indexed": existing_count}

        logger.info("indexing_drug_chunks", count=len(chunks))
        texts = [c.content for c in chunks]
        embeddings = self._embed_texts(texts, desc="Embedding drug evidence")

        batch_size = 200
        for i in tqdm(range(0, len(chunks), batch_size), desc="Indexing drugs"):
            batch_chunks = chunks[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]

            # Re-fetch collection on every batch to avoid stale-ref bug
            coll = self._get_collection(collection_name)
            coll.upsert(
                ids=[c.chunk_id for c in batch_chunks],
                embeddings=batch_embeddings,
                documents=[c.content for c in batch_chunks],
                metadatas=[
                    {
                        "source_type": "drug_evidence",
                        "drug_id": c.drug_id or "",
                        "drug_name": c.drug_name or "",
                        "primary_indication": (c.primary_indication or "")[:200],
                        "category": c.category or "",
                        "tier": c.tier or "",
                        "clinical_relevance": c.clinical_relevance or "",
                        "section_type": c.section_type or "",
                        "target_patient_factors": json.dumps(c.target_patient_factors or []),
                        "has_boxed_warning": bool(c.has_boxed_warning),
                        "has_contraindications": bool(c.has_contraindications),
                        "data_source": c.data_source or "",
                        "schema_version": c.schema_version or "",
                        "word_count": c.word_count or 0,
                        "aliases": json.dumps(c.aliases or []),
                    }
                    for c in batch_chunks
                ],
            )

        logger.info("drug_indexing_complete", chunks=len(chunks))
        return {"chunks_indexed": len(chunks)}

    def _build_bm25_index(
        self,
        chunks: list[str],
        ids: list[str],
        index_name: str,
    ) -> None:
        """Build and persist a BM25 index for lexical retrieval."""
        if not chunks:
            return

        logger.info("building_bm25_index", name=index_name, docs=len(chunks))
        # Use medical-aware tokenization (matches retriever tokenization)
        tokenized = [_tokenize_bm25(doc) for doc in chunks]
        bm25 = BM25Okapi(tokenized)

        index_path = self.settings.bm25_index_dir / f"{index_name}_bm25.pkl"
        with open(index_path, "wb") as f:
            pickle.dump({"bm25": bm25, "ids": ids, "documents": chunks}, f)

        logger.info("bm25_index_saved", path=str(index_path))
