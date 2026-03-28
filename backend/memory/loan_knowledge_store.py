"""
LoanKnowledgeStore — ChromaDB wrapper for bank loan product knowledge.

Design:
    - ONE global collection: 'loan_products'  (NOT per-customer — this is product data)
    - Each loan product is chunked into ~6 semantic sections for precise retrieval
    - Metadata: loan_id, loan_type, section (overview/eligibility/rates/documents/faq/schemes)
    - Idempotent ingestion — re-running ingest won't duplicate docs (upsert by chunk_id)

Sections per product:
    overview    → name, purpose, tagline, eligible_for
    eligibility → age, income, cibil, foir, vintage, collateral
    rates       → interest slabs, special concessions, processing fee, prepayment
    documents   → all document categories flattened to text
    faq         → each Q&A pair as a separate chunk
    schemes     → linked government schemes and special features
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import chromadb
from chromadb.config import Settings

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_PATH

logger = logging.getLogger(__name__)

LOAN_COLLECTION_NAME = "loan_products"
LOAN_SEARCH_TOP_K = 4


class LoanKnowledgeStore:
    """
    Global ChromaDB collection for bank loan product knowledge.
    Shared across all customers — product data, not customer data.
    """

    def __init__(self, persist_path: str = CHROMA_PATH):
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(
            name=LOAN_COLLECTION_NAME,
            metadata={"description": "Bank loan product knowledge base"},
        )
        logger.info(
            f"LoanKnowledgeStore ready — collection '{LOAN_COLLECTION_NAME}' "
            f"({self.collection.count()} docs)"
        )

    # =========================================================================
    # SEARCH — primary API used by the agent tool
    # =========================================================================

    def search(
        self,
        query: str,
        n_results: int = LOAN_SEARCH_TOP_K,
        loan_type: Optional[str] = None,
        section: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over loan product knowledge.

        Args:
            query:     Natural language query (e.g. "home loan eligibility income requirement")
            n_results: Max chunks to return
            loan_type: Filter by loan type slug (e.g. "home_loan", "gold_loan")
            section:   Filter by section ("overview", "eligibility", "rates", "documents", "faq", "schemes")

        Returns:
            List of dicts: {chunk_id, text, metadata, distance}
        """
        if self.collection.count() == 0:
            logger.warning("LoanKnowledgeStore is empty — run ingest_loan_data.py first!")
            return []

        # Build where filter
        conditions = []
        if loan_type:
            conditions.append({"loan_type": loan_type})
        if section:
            conditions.append({"section": section})

        where = None
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count()),
                where=where,
            )
        except Exception as e:
            logger.error(f"LoanKnowledgeStore search failed: {e}")
            return []

        output = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                output.append({
                    "chunk_id": results["ids"][0][i],
                    "text":     doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

        return output

    def format_for_prompt(
        self,
        query: str,
        n_results: int = LOAN_SEARCH_TOP_K,
        distance_threshold: float = 1.2,  # ChromaDB cosine distance — lower = more similar
    ) -> str:
        """
        Run search and format results as a ready-to-inject prompt block.
        Returns empty string if no relevant results found.

        Args:
            query:              The user's query / rewritten retrieval query
            n_results:          Max chunks to retrieve
            distance_threshold: Chunks with distance above this are dropped (not relevant)

        Returns:
            Formatted string for injection into LLM context, or "" if nothing useful.
        """
        results = self.search(query, n_results=n_results)

        # Filter out low-relevance results
        relevant = [r for r in results if (r["distance"] is None or r["distance"] <= distance_threshold)]

        if not relevant:
            return ""

        lines = ["=== BANK LOAN PRODUCT KNOWLEDGE ==="]
        seen_loan_types = set()

        for r in relevant:
            meta       = r["metadata"]
            loan_name  = meta.get("loan_name", "")
            loan_type  = meta.get("loan_type", "")
            section    = meta.get("section", "")
            header     = f"[{loan_name} — {section.upper()}]" if loan_name else f"[{section.upper()}]"

            if loan_type and loan_type not in seen_loan_types:
                seen_loan_types.add(loan_type)

            lines.append(f"\n{header}")
            lines.append(r["text"])

        return "\n".join(lines)

    # =========================================================================
    # INGESTION — called by ingest_loan_data.py
    # =========================================================================

    def ingest_loan_products(self, json_path: str) -> int:
        """
        Load loan_products.json and ingest all products into ChromaDB.
        Idempotent — uses upsert, so safe to re-run.

        Args:
            json_path: Path to loan_products.json

        Returns:
            Number of chunks ingested
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        products = data.get("loan_products", [])
        total_chunks = 0

        for product in products:
            chunks = self._chunk_product(product)
            for chunk_id, text, metadata in chunks:
                self.collection.upsert(
                    ids=[chunk_id],
                    documents=[text],
                    metadatas=[metadata],
                )
                total_chunks += 1

        logger.info(f"Ingested {total_chunks} chunks from {len(products)} loan products")
        return total_chunks

    def _chunk_product(self, product: Dict[str, Any]):
        """
        Split one loan product dict into semantic chunks.
        Yields: (chunk_id, text, metadata)
        """
        loan_id   = product.get("id", "UNKNOWN")
        loan_type = product.get("type", "").lower().replace(" ", "_").replace("/", "_")
        loan_name = product.get("name", "")
        base_meta = {
            "loan_id":   loan_id,
            "loan_type": loan_type,
            "loan_name": loan_name,
        }

        # ── OVERVIEW ─────────────────────────────────────────────────────────
        eligible_for = product.get("eligible_for", [])
        overview_text = (
            f"Loan: {loan_name} ({product.get('type', '')})\n"
            f"ID: {loan_id}\n"
            f"Tagline: {product.get('tagline', '')}\n"
            f"Purpose: {product.get('purpose', '')}\n"
            f"Who can apply: {'; '.join(eligible_for)}"
        )
        yield (
            f"{loan_id}_overview",
            overview_text,
            {**base_meta, "section": "overview"},
        )

        # ── ELIGIBILITY ──────────────────────────────────────────────────────
        ec = product.get("eligibility_criteria", {})
        elig_lines = []
        if "age" in ec:
            a = ec["age"]
            elig_lines.append(f"Age: {a.get('min')}–{a.get('max')} years. {a.get('note','')}")
        if "minimum_income" in ec:
            mi = ec["minimum_income"]
            elig_lines.append(
                f"Min income: salaried ₹{mi.get('salaried','N/A')}/mo, "
                f"self-employed ₹{mi.get('self_employed','N/A')}/mo"
            )
        if "cibil_score" in ec:
            c = ec["cibil_score"]
            if isinstance(c, dict):
                elig_lines.append(f"CIBIL: min {c.get('min','N/A')}, preferred {c.get('preferred','N/A')}")
            else:
                elig_lines.append(f"CIBIL: {c}")
        if "foir" in ec:
            elig_lines.append(f"FOIR (debt-to-income): max {ec['foir'].get('max_percent','N/A')}%")
        if "loan_to_value" in ec:
            elig_lines.append(f"LTV: up to {ec['loan_to_value'].get('max_percent','N/A')}% of property value")
        if "business_vintage" in ec:
            bv = ec["business_vintage"]
            elig_lines.append(f"Business vintage: min {bv.get('min_years','N/A')} years profitable. {bv.get('note','')}")
        if "minimum_employment" in ec:
            me = ec["minimum_employment"]
            elig_lines.append(f"Employment: current job {me.get('current_employer','?')}, total {me.get('total_experience','?')}")
        if "annual_turnover" in ec:
            elig_lines.append(f"Min annual turnover: ₹{ec['annual_turnover'].get('min','N/A'):,}")
        if "land_ownership" in ec:
            elig_lines.append(f"Land: {ec['land_ownership'].get('note','')}")
        if "admission" in ec:
            elig_lines.append(f"Admission: {ec['admission']}")
        if "academic_performance" in ec:
            ap = ec["academic_performance"]
            elig_lines.append(f"Academic: min {ap.get('min_percentage','N/A')}% in qualifying exam")

        # Add loan amount and tenure to eligibility chunk (sizing criteria)
        la = product.get("loan_amount", {})
        if la:
            if isinstance(la, dict) and "min" in la:
                elig_lines.append(f"Loan amount: ₹{la['min']:,} to ₹{la['max']:,}")
            elif isinstance(la, dict):
                for k, v in la.items():
                    if isinstance(v, dict) and "max" in v:
                        elig_lines.append(f"Loan amount ({k}): up to ₹{v['max']:,}. {v.get('note','')}")

        ten = product.get("tenure", {})
        if isinstance(ten, dict):
            tenure_parts = []
            for k, v in ten.items():
                if k != "note":
                    tenure_parts.append(f"{k}: {v}")
            if tenure_parts:
                elig_lines.append(f"Tenure: {'; '.join(tenure_parts)}")

        collateral = product.get("collateral", None)
        if collateral:
            if isinstance(collateral, dict):
                col_parts = [f"{k}: {v}" for k, v in collateral.items()]
                elig_lines.append(f"Collateral: {'; '.join(col_parts)}")
            elif isinstance(collateral, str):
                elig_lines.append(f"Collateral: {collateral}")

        yield (
            f"{loan_id}_eligibility",
            f"ELIGIBILITY — {loan_name}\n" + "\n".join(elig_lines),
            {**base_meta, "section": "eligibility"},
        )

        # ── INTEREST RATES & FEES ────────────────────────────────────────────
        ir = product.get("interest_rates", {})
        rate_lines = [f"Rate type: {ir.get('base_rate_type', 'N/A')}"]

        slabs = ir.get("slabs", [])
        for s in slabs:
            slab_parts = []
            if "cibil_range" in s:
                slab_parts.append(f"CIBIL {s['cibil_range']}")
            if "category" in s:
                slab_parts.append(s["category"])
            if "rate_percent" in s:
                slab_parts.append(f"{s['rate_percent']}%")
            rate_lines.append("  Rate slab: " + " | ".join(slab_parts))

        # Special concessions
        for k in ["special_rates", "concessions", "employer_category_discount", "special"]:
            v = ir.get(k, {})
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if kk != "unit":
                        rate_lines.append(f"  Concession [{kk}]: {vv}")

        # Government subvention (agri loan)
        subv = ir.get("interest_subvention", {})
        if subv:
            rate_lines.append(f"  Govt subvention: {subv.get('benefit', '')} — effective rate {subv.get('effective_rate_if_timely', '')}%")

        # MUDRA rates
        mudra = ir.get("government_scheme_rates", {})
        for scheme, v in mudra.items():
            if isinstance(v, dict):
                rate_lines.append(f"  {scheme}: limit ₹{v.get('limit',0):,} at {v.get('rate_percent','?')}%")

        # Processing fee
        pf = product.get("processing_fee", {})
        if isinstance(pf, dict):
            fee_str = f"Processing fee: {pf.get('percent','?')}% (min ₹{pf.get('min','?')}, max ₹{pf.get('max','?')})"
            rate_lines.append(fee_str)
        elif isinstance(pf, str):
            rate_lines.append(f"Processing fee: {pf}")

        # Prepayment
        pp = product.get("prepayment", {})
        if isinstance(pp, dict):
            for k, v in pp.items():
                rate_lines.append(f"Prepayment ({k}): {v}")
        elif isinstance(pp, str):
            rate_lines.append(f"Prepayment: {pp}")

        yield (
            f"{loan_id}_rates",
            f"INTEREST RATES & FEES — {loan_name}\n" + "\n".join(rate_lines),
            {**base_meta, "section": "rates"},
        )

        # ── REQUIRED DOCUMENTS ───────────────────────────────────────────────
        docs = product.get("required_documents", {})
        doc_lines = []
        for category, items in docs.items():
            if isinstance(items, list):
                doc_lines.append(f"{category.replace('_', ' ').title()}: {', '.join(items)}")
            elif isinstance(items, str):
                doc_lines.append(f"{category.replace('_', ' ').title()}: {items}")

        if doc_lines:
            yield (
                f"{loan_id}_documents",
                f"REQUIRED DOCUMENTS — {loan_name}\n" + "\n".join(doc_lines),
                {**base_meta, "section": "documents"},
            )

        # ── FAQ ──────────────────────────────────────────────────────────────
        faqs = product.get("faq", [])
        if faqs:
            faq_lines = []
            for item in faqs:
                faq_lines.append(f"Q: {item.get('q', '')}")
                faq_lines.append(f"A: {item.get('a', '')}")
            yield (
                f"{loan_id}_faq",
                f"FAQ — {loan_name}\n" + "\n".join(faq_lines),
                {**base_meta, "section": "faq"},
            )

        # ── SCHEMES / SPECIAL FEATURES ───────────────────────────────────────
        scheme_lines = []
        for key in ["special_schemes", "government_schemes", "government_schemes_linked", "special_features"]:
            items = product.get(key, [])
            if items:
                scheme_lines.extend(items)

        if scheme_lines:
            yield (
                f"{loan_id}_schemes",
                f"SPECIAL SCHEMES & FEATURES — {loan_name}\n" + "\n".join(f"• {s}" for s in scheme_lines),
                {**base_meta, "section": "schemes"},
            )

    # =========================================================================
    # UTILS
    # =========================================================================

    def count(self) -> int:
        return self.collection.count()

    def list_loan_types(self) -> List[str]:
        """Return all distinct loan_type values in the collection."""
        try:
            results = self.collection.get(include=["metadatas"])
            types = {m.get("loan_type", "") for m in results["metadatas"] if m}
            return sorted(types - {""})
        except Exception:
            return []

    def clear(self):
        """Wipe and recreate the loan_products collection (for re-ingestion)."""
        self.client.delete_collection(LOAN_COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=LOAN_COLLECTION_NAME,
            metadata={"description": "Bank loan product knowledge base"},
        )
        logger.info("loan_products collection cleared")
