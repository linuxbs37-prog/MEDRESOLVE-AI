"""
MEDRESOLVE AI — Drug Knowledge Base Ingestion Script
Run this FIRST to build the drug knowledge base from drug data.
Usage: python scripts/ingest.py [--force]
"""

import sys
import os
# Force UTF-8 output on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import argparse
import structlog
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console(force_terminal=True, highlight=False)


def setup_logging():
    structlog.configure(
        processors=[
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
    )


def main():
    parser = argparse.ArgumentParser(description="MEDRESOLVE AI Knowledge Base Ingestion")
    parser.add_argument("--force", action="store_true", help="Force rebuild (drops existing collections)")
    args = parser.parse_args()

    setup_logging()

    console.print(Panel.fit(
        "[bold blue]MEDRESOLVE AI -- Drug Knowledge Base Ingestion[/bold blue]\n"
        "[dim]Building drug evidence index...[/dim]",
        border_style="blue",
        box=box.DOUBLE,
    ))

    # Check API key
    from medresolve.config import get_settings
    settings = get_settings()

    if not settings.google_api_key or settings.google_api_key == "your_google_api_key_here":
        console.print("[yellow]WARNING: GOOGLE_API_KEY not set. LLM features will not work.[/yellow]")
        console.print("[dim]   Set it in .env file: GOOGLE_API_KEY=your_key_here[/dim]")
    else:
        console.print("[green]OK: Google Gemini API Key found[/green]")

    console.print(f"[dim]Embedding model: {settings.embedding_model}[/dim]")
    console.print(f"[dim]ChromaDB path: {settings.chroma_persist_dir}[/dim]")
    console.print(f"[dim]Drug KB dir: {settings.drug_kb_dir}[/dim]")

    if args.force:
        console.print("[bold yellow]⚠️  Force rebuild enabled — dropping existing collections[/bold yellow]")

    console.print("\n[bold]Starting ingestion pipeline...[/bold]\n")

    from medresolve.ingestion.pipeline import MedResolveIngestionPipeline

    pipeline = MedResolveIngestionPipeline()
    stats = pipeline.run(force_rebuild=args.force)

    # Show results
    table = Table(title="Ingestion Results", box=box.ROUNDED, border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")

    table.add_row("Drug Chunks Indexed", str(stats.get("drug_chunks_indexed", 0)))
    table.add_row("Total Chunks", str(stats.get("total_chunks", 0)))
    table.add_row("Time Elapsed", f"{stats.get('elapsed_seconds', 0):.1f}s")

    console.print(table)

    console.print(Panel.fit(
        "[bold green]Ingestion Complete![/bold green]\n\n"
        "Next steps:\n"
        "  1. Run the Streamlit UI:  [bold]streamlit run ui/app.py[/bold]\n"
        "  2. Or run the FastAPI:   [bold]uvicorn medresolve.api.app:app --reload[/bold]\n"
        "  3. Or test directly:     [bold]python scripts/demo.py[/bold]",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
