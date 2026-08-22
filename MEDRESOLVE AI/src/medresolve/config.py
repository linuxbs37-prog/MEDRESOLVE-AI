"""
MEDRESOLVE AI — Central Configuration
All settings are managed here with Pydantic Settings.
Drug-only system — guideline configuration removed.
"""

from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── Project Root ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    """Application settings — loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM (Google Gemini) ───────────────────────────────────────────────────
    google_api_key: str = Field(default="", description="Google Gemini API key (aistudio.google.com)")
    gemini_model: str = "gemini-3.6-flash"  # Free tier — stable Flash model (released July 2026)
    gemini_temperature: float = 0.1  # Low temp for medical accuracy
    gemini_max_tokens: int = 4096

    # ── Embeddings (local, free) ──────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"  # Fast CPU-friendly model (~5x faster than bge-large)
    embedding_device: str = "cpu"  # "cuda" if GPU available
    embedding_batch_size: int = 64

    # ── Reranker (local, free) ────────────────────────────────────────────────
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    reranker_top_k: int = 8  # Keep top-k after reranking

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_persist_dir: Path = PROJECT_ROOT / "data" / "chroma_db"
    chroma_drug_collection: str = "medresolve_drugs"

    # ── BM25 ─────────────────────────────────────────────────────────────────
    bm25_index_dir: Path = PROJECT_ROOT / "data" / "bm25_indexes"

    # ── Data Paths ────────────────────────────────────────────────────────────
    drug_kb_dir: Path = PROJECT_ROOT / "drug_knowledge_base"

    # ── Retrieval Parameters ──────────────────────────────────────────────────
    retrieval_dense_k: int = 12       # Dense retrieval candidates (P1-E: was dead, now wired)
    retrieval_bm25_k: int = 12        # BM25 retrieval candidates (P1-E: was dead, now wired)
    retrieval_final_k: int = 4        # After reranking (token-efficient)
    retrieval_drug_k: int = 3         # Drug evidence chunks to keep (token-efficient)
    min_relevance_score: float = 0.35  # Minimum score to include evidence

    # ── Retrieval Quality Thresholds ──────────────────────────────────────────
    # P1-RET-4 fix: raised from 0.0 to 0.5.
    # Cross-encoder scores range ~[-10, +10]. A threshold of 0.0 lets almost
    # everything pass. 0.5 filters clearly irrelevant chunks while preserving
    # borderline useful ones. Tune this against eval/results/ if recall drops.
    reranker_score_threshold: float = 0.5   # Min cross-encoder score to keep a chunk
    retrieval_min_chunks_risk: int = 3      # Min chunks required for risk report
    retrieval_min_chunks_chat: int = 1      # Min chunks required for chat response
    max_reretrieval_attempts: int = 1       # Max retry attempts if evidence insufficient

    # ── Retrieval Hard Limits (P1-F: previously hardcoded in nodes.py) ─────────
    max_retrieval_drugs: int = 2       # Max drug IDs processed per query
    max_retrieval_factors: int = 4     # Max patient factors used in subquery generation
    max_subqueries: int = 5            # Max total subqueries generated
    max_subqueries_per_drug: int = 4   # Max subqueries executed per drug ID
    max_risk_factors: int = 5          # Max factors assessed in NO_DATA fallback

    # ── Chunking ──────────────────────────────────────────────────────────────
    # NOTE (P1-CHUNK-4): These values are defined for future sliding-window chunking.
    # The current ingestion strategy is per-section (one chunk per clinical section
    # per drug), so chunk_size/chunk_overlap/min_chunk_size are NOT currently applied
    # by drug_normalizer.py. The 1500-char hard limit in _sentence_split_at() acts
    # as the de-facto max chunk size. These settings are kept for planned future use.
    chunk_size: int = 1200            # Target chars per chunk (not yet applied — see note above)
    chunk_overlap: int = 200          # Overlap between chunks (not yet applied — see note above)
    min_chunk_size: int = 300         # Discard chunks smaller than this (not yet applied)

    # ── CORS (P4-A) ───────────────────────────────────────────────────────────
    cors_allowed_origins: list[str] = ["*"]   # Set to specific origins in production

    # ── LangSmith (optional tracing) ──────────────────────────────────────────
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "medresolve-ai"

    # ── Safety ────────────────────────────────────────────────────────────────
    max_query_length: int = 2000
    enable_safety_gate: bool = True
    enable_safety_gate_llm: bool = False    # Disable LLM safety gate — use deterministic only

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.bm25_index_dir.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)
        self.drug_kb_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — call this everywhere."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
