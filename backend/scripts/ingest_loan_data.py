"""
Ingest Loan Products into ChromaDB.

Run once (or after updating loan_products.json):

    cd /Users/pandhari/Desktop/LoanAgent/backend
    python scripts/ingest_loan_data.py

Options:
    --clear    Wipe existing loan_products collection before ingesting (re-index)
    --dry-run  Show what would be ingested without writing to ChromaDB
    --json     Path to JSON file (default: data/loan_products.json)
"""

import sys
import json
import logging
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_loan_data")


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest loan products into ChromaDB")
    parser.add_argument(
        "--json",
        default=str(PROJECT_ROOT / "data" / "loan_products.json"),
        help="Path to loan_products.json (default: data/loan_products.json)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing loan_products collection before ingesting",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show chunks that would be ingested without writing to ChromaDB",
    )
    return parser.parse_args()


def dry_run(json_path: str):
    """Show all chunks that would be generated without writing anything."""
    from memory.loan_knowledge_store import LoanKnowledgeStore

    store = LoanKnowledgeStore()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("loan_products", [])
    total = 0

    print("\n" + "=" * 70)
    print("DRY RUN — Chunks that would be ingested")
    print("=" * 70)

    for product in products:
        print(f"\n📋 {product.get('name')} ({product.get('id')})")
        chunks = list(store._chunk_product(product))
        for chunk_id, text, metadata in chunks:
            preview = text[:100].replace("\n", " ") + "..."
            print(f"   [{metadata['section']:12}] {chunk_id}")
            print(f"                  {preview}")
            total += 1

    print(f"\n✅ Total chunks: {total} from {len(products)} products")
    print("=" * 70)
    return total


def main():
    args = parse_args()
    json_path = Path(args.json)

    if not json_path.exists():
        logger.error(f"JSON file not found: {json_path}")
        logger.info("Create data/loan_products.json first — see the generated file from Claude")
        sys.exit(1)

    # ── Dry run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        dry_run(str(json_path))
        return

    # ── Real ingestion ────────────────────────────────────────────────────────
    from memory.loan_knowledge_store import LoanKnowledgeStore

    store = LoanKnowledgeStore()

    if args.clear:
        logger.info("Clearing existing loan_products collection...")
        store.clear()
        logger.info("✅ Collection cleared")

    pre_count = store.count()
    logger.info(f"Collection before ingestion: {pre_count} docs")

    print("\n" + "=" * 70)
    print("Ingesting Loan Products → ChromaDB")
    print(f"Source: {json_path}")
    print("=" * 70)

    total = store.ingest_loan_products(str(json_path))

    post_count = store.count()

    print(f"\n✅ Ingestion complete!")
    print(f"   Chunks written : {total}")
    print(f"   Collection size: {post_count} docs")
    print(f"   Loan types     : {', '.join(store.list_loan_types())}")

    # ── Smoke test ────────────────────────────────────────────────────────────
    print("\n" + "-" * 70)
    print("Smoke test — 3 sample queries:")
    print("-" * 70)

    test_queries = [
        "home loan interest rate for CIBIL 750",
        "documents required for agriculture KCC loan",
        "MSME business loan eligibility annual turnover",
    ]

    for q in test_queries:
        results = store.search(q, n_results=2)
        print(f"\n  Query: '{q}'")
        for r in results:
            meta = r["metadata"]
            print(f"    → [{meta.get('loan_id')} / {meta.get('section')}] dist={r['distance']:.3f}")
            print(f"       {r['text'][:80].replace(chr(10), ' ')}...")

    print("\n" + "=" * 70)
    print("Loan knowledge base is ready for agent use.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
