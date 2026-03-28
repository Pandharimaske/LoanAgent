"""
Memory Retriever — Context Builder for LoanAgent.

Builds a compact, token-efficient memory_prompt_block from 2 tiers:

  Tier 1 → SQLite  : All known structured facts (income, CIBIL, employment …)
  Tier 2 → ChromaDB: Top-K contextual chunks for things NOT in the schema
                     (goals, concerns, references, soft preferences …)

Session summaries (Tier 3) are only included when they exist AND contain
real LLM-generated content — NOT template strings.  The check is simple:
if a summary starts with "Session " it's a legacy template and is skipped.

Design goal: every token in memory_prompt_block must earn its place.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import CustomerMemory
from config import VECTOR_SEARCH_TOP_K

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Builds the memory_prompt_block injected into every LLM call.
    Accepts optional pre-created db / vector_store to avoid redundant connections.
    """

    def __init__(
        self,
        db: Optional[MemoryDatabase] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        self.db = db or MemoryDatabase()
        self.vector_store = vector_store or VectorStore()
        if not self.db.connection:
            self.db.connect()
        self.db.init_schema()

    # ------------------------------------------------------------------ public

    def build_context(
        self,
        customer_id: str,
        current_turn: str,
        n_chunks: int = VECTOR_SEARCH_TOP_K,
        n_summaries: int = 2,
    ) -> Dict[str, Any]:
        """
        Build the complete memory context for one agent turn.

        Returns:
            {
              'prompt_block'     : str  — ready to inject into LLM prompt
              'structured_facts' : str  — Tier 1 human-readable lines
              'relevant_chunks'  : list — Tier 2 raw ChromaDB results
              'session_summaries': list — Tier 3 raw ChromaDB results (filtered)
              'customer_found'   : bool
            }
        """
        # Tier 1 — SQLite facts
        structured_facts, customer_found = self._load_sqlite_facts(customer_id)

        # Tier 2 — ChromaDB contextual chunks
        relevant_chunks = self._search_chunks(customer_id, current_turn, n_chunks)

        # Tier 3 — ChromaDB session summaries (real LLM output only)
        session_summaries = self._load_summaries(customer_id, n_summaries)

        prompt_block = self._format_prompt_block(
            structured_facts=structured_facts,
            relevant_chunks=relevant_chunks,
            session_summaries=session_summaries,
        )

        return {
            "prompt_block":      prompt_block,
            "structured_facts":  structured_facts,
            "relevant_chunks":   relevant_chunks,
            "session_summaries": session_summaries,
            "customer_found":    customer_found,
        }

    # ----------------------------------------------------------------- private

    def _load_sqlite_facts(self, customer_id: str) -> tuple[str, bool]:
        """Return (human-readable facts string, customer_found bool)."""
        try:
            memory = self.db.load_customer_memory(customer_id)
        except Exception as e:
            logger.error(f"SQLite load failed for {customer_id}: {e}")
            return "[Memory load error]", False

        if not memory:
            return "New customer — no profile data yet.", False

        lines = []

        # Identity
        if memory.full_name:        lines.append(f"Name: {memory.full_name}")
        if memory.phone:            lines.append(f"Phone: {memory.phone}")
        if memory.date_of_birth:    lines.append(f"DOB: {memory.date_of_birth}")

        # Address
        if memory.city or memory.state:
            loc = ", ".join(filter(None, [memory.city, memory.state, memory.pincode]))
            lines.append(f"Location: {loc}")
        if memory.address:          lines.append(f"Address: {memory.address}")

        # Employment
        if memory.employer_name:    lines.append(f"Employer: {memory.employer_name}")
        if memory.job_title:        lines.append(f"Job: {memory.job_title}")
        if memory.years_at_job:     lines.append(f"Experience: {memory.years_at_job} yrs")

        # Income
        if memory.monthly_income:   lines.append(f"Monthly Income: ₹{memory.monthly_income:,.0f}")
        if memory.income_type:      lines.append(f"Income Type: {memory.income_type}")

        # Credit
        if memory.cibil_score:      lines.append(f"CIBIL: {memory.cibil_score}")
        if memory.total_existing_emi_monthly:
            lines.append(f"Existing EMI: ₹{memory.total_existing_emi_monthly:,.0f}/mo")
        if memory.number_of_active_loans is not None:
            lines.append(f"Active Loans: {memory.number_of_active_loans}")

        # Loan request
        if memory.requested_loan_amount:
            lines.append(f"Loan Requested: ₹{memory.requested_loan_amount:,.0f}")
        if memory.requested_loan_type:
            lines.append(f"Loan Type: {memory.requested_loan_type}")
        if memory.requested_tenure_months:
            lines.append(f"Tenure: {memory.requested_tenure_months} months")
        if memory.loan_purpose:
            lines.append(f"Purpose: {memory.loan_purpose}")

        # Co-applicant
        if memory.coapplicant_name:
            co_line = f"Co-applicant: {memory.coapplicant_name}"
            if memory.coapplicant_relation:
                co_line += f" ({memory.coapplicant_relation})"
            if memory.coapplicant_income:
                co_line += f", income ₹{memory.coapplicant_income:,.0f}"
            lines.append(co_line)

        # Application status
        lines.append(f"Application: {memory.application_status.upper()}")
        if memory.documents_submitted:
            lines.append(f"Documents: {memory.documents_submitted}")

        return "\n".join(lines), True

    def _search_chunks(
        self, customer_id: str, query: str, n_results: int
    ) -> List[Dict]:
        """Return top-K ChromaDB chunks relevant to the query."""
        try:
            return self.vector_store.search_chunks(
                customer_id=customer_id,
                query_text=query,
                n_results=n_results,
            )
        except Exception as e:
            logger.warning(f"ChromaDB chunk search failed: {e}")
            return []

    def _load_summaries(self, customer_id: str, n: int) -> List[Dict]:
        """
        Load last-N session summaries, filtering out legacy template strings.
        A summary is a template if it starts with "Session " — those are useless
        noise written by the old end_session and should not consume context tokens.
        """
        try:
            all_summaries = self.vector_store.get_last_n_summaries(customer_id, n=n)
        except Exception as e:
            logger.warning(f"ChromaDB summary load failed: {e}")
            return []

        real_summaries = []
        for s in all_summaries:
            text = s.get("document", "")
            # Skip fake template summaries
            if text.startswith("Session ") and "turns" in text and "Last response:" in text:
                continue
            if text.strip():
                real_summaries.append(s)

        return real_summaries

    def _format_prompt_block(
        self,
        structured_facts: str,
        relevant_chunks: List[Dict],
        session_summaries: List[Dict],
    ) -> str:
        """
        Assemble the memory block injected into every LLM system prompt.
        Token-efficient: each section only appears when it has real content.
        """
        sections: List[str] = []

        # --- Tier 1: Customer Profile ---
        sections.append("=== CUSTOMER PROFILE ===")
        sections.append(structured_facts or "No profile data yet.")

        # --- Tier 2: Contextual memory (ChromaDB chunks) ---
        # Only show if there are genuinely useful contextual chunks
        if relevant_chunks:
            sections.append("\n=== RELEVANT CONTEXT (from past conversations) ===")
            for chunk in relevant_chunks:
                meta    = chunk.get("metadata", {})
                topic   = meta.get("topic_tag", "")
                topic_s = f"[{topic}] " if topic and topic not in ("user_input", "general") else ""
                text    = chunk.get("document", "")
                if text:
                    sections.append(f"• {topic_s}{text}")

        # --- Tier 3: Cross-session summaries (real LLM output only) ---
        if session_summaries:
            sections.append("\n=== PREVIOUS SESSION SUMMARIES ===")
            for s in session_summaries:
                text = s.get("document", "").strip()
                if text:
                    sections.append(f"• {text}")

        return "\n".join(sections)

    # ------------------------------------------------------------------ utils

    def get_facts_summary(self, customer_id: str) -> str:
        """Flat one-liner of key facts — used for quick mismatch comparisons."""
        try:
            memory = self.db.load_customer_memory(customer_id)
            if not memory:
                return ""
            parts = []
            if memory.monthly_income:      parts.append(f"income=₹{memory.monthly_income:,.0f}")
            if memory.cibil_score:         parts.append(f"cibil={memory.cibil_score}")
            if memory.requested_loan_amount: parts.append(f"loan=₹{memory.requested_loan_amount:,.0f}")
            if memory.requested_loan_type: parts.append(f"type={memory.requested_loan_type}")
            if memory.full_name:           parts.append(f"name={memory.full_name}")
            if memory.city:                parts.append(f"city={memory.city}")
            if memory.employer_name:       parts.append(f"employer={memory.employer_name}")
            return " | ".join(parts)
        except Exception as e:
            logger.error(f"get_facts_summary failed: {e}")
            return ""

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
