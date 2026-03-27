"""
Memory Retriever — Context Builder for LoanAgent.

Combines all 3 memory tiers into a single formatted context string
ready for injection into the LLM system prompt.

Tier 1 → SQLite: Confirmed structured facts (income, CIBIL, co-applicant, etc.)
Tier 2 → ChromaDB: Top-K semantically relevant conversation chunks
Tier 3 → ChromaDB: Last N session summaries (chronological)

Output is a clean, human-readable block the SLM can reason over.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.sqlite_store_simplified import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import CustomerMemory
from config import VECTOR_SEARCH_TOP_K

logger = logging.getLogger(__name__)





# ============================================================================
# MAIN RETRIEVER
# ============================================================================


class MemoryRetriever:
    """
    Combines all 3 memory tiers into a single prompt-ready context block.

    Usage:
        retriever = MemoryRetriever()
        context = retriever.build_context(
            customer_id="RAJESH_001",
            current_turn="What was my income again?",
        )
    """

    def __init__(
        self,
        db: Optional[MemoryDatabase] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        """
        Initialize retriever with optional pre-existing instances.
        Creates new instances if not provided.
        """
        self.db = db or MemoryDatabase()
        self.vector_store = vector_store or VectorStore()

        # Ensure DB is connected and schema exists
        self.db.connect()
        self.db.init_schema()

    def build_context(
        self,
        customer_id: str,
        current_turn: str,
        n_chunks: int = VECTOR_SEARCH_TOP_K,
        n_summaries: int = 2,
    ) -> Dict[str, Any]:
        """
        Build the full memory context for the current agent turn.

        Args:
            customer_id: The customer whose memory to retrieve.
            current_turn: The current user message (used for semantic search).
            n_chunks: How many relevant chunks to retrieve from ChromaDB.
            n_summaries: How many past session summaries to include.
            include_pii: Whether to include PII facts (name, phone, etc.).

        Returns:
            Dict with keys:
                - 'prompt_block': str — formatted context to inject into prompt
                - 'structured_facts': str — Tier 1 facts only
                - 'relevant_chunks': List — Tier 2 raw results
                - 'session_summaries': List — Tier 3 raw summaries
                - 'customer_found': bool
        """
        structured_facts = ""
        relevant_chunks = []
        session_summaries = []
        customer_found = False

        # ---- Tier 1: SQLite Structured Facts ----
        try:
            memory = self.db.load_customer_memory(customer_id)
            if memory:
                customer_found = True
                # Build facts from the flat schema
                lines = []
                # Identity
                if memory.full_name and memory.full_name_status:
                    lines.append(f"  • Full Name: {memory.full_name} [{memory.full_name_status.upper()}]")
                if memory.email and memory.email_status:
                    lines.append(f"  • Email: {memory.email} [{memory.email_status.upper()}]")
                if memory.phone and memory.phone_status:
                    lines.append(f"  • Phone: {memory.phone} [{memory.phone_status.upper()}]")
                # Address
                if memory.city and memory.city_status:
                    lines.append(f"  • City: {memory.city} [{memory.city_status.upper()}]")
                if memory.state and memory.state_status:
                    lines.append(f"  • State: {memory.state} [{memory.state_status.upper()}]")
                # Employment
                if memory.employer_name and memory.employer_name_status:
                    lines.append(f"  • Employer: {memory.employer_name} [{memory.employer_name_status.upper()}]")
                if memory.job_title and memory.job_title_status:
                    lines.append(f"  • Job Title: {memory.job_title} [{memory.job_title_status.upper()}]")
                if memory.total_work_experience_years and memory.total_work_experience_years_status:
                    lines.append(f"  • Work Experience: {memory.total_work_experience_years} years [{memory.total_work_experience_years_status.upper()}]")
                # Income
                if memory.monthly_income and memory.monthly_income_status:
                    lines.append(f"  • Monthly Income: ₹{memory.monthly_income} [{memory.monthly_income_status.upper()}]")
                if memory.annual_income and memory.annual_income_status:
                    lines.append(f"  • Annual Income: ₹{memory.annual_income} [{memory.annual_income_status.upper()}]")
                # Credit
                if memory.cibil_score and memory.cibil_score_status:
                    lines.append(f"  • CIBIL Score: {memory.cibil_score} [{memory.cibil_score_status.upper()}]")
                if memory.total_existing_emi_monthly and memory.total_existing_emi_monthly_status:
                    lines.append(f"  • Existing EMI (monthly): ₹{memory.total_existing_emi_monthly} [{memory.total_existing_emi_monthly_status.upper()}]")
                if memory.number_of_active_loans and memory.number_of_active_loans_status:
                    lines.append(f"  • Active Loans: {memory.number_of_active_loans} [{memory.number_of_active_loans_status.upper()}]")
                # Loan Request
                if memory.requested_loan_amount and memory.requested_loan_amount_status:
                    lines.append(f"  • Loan Amount Requested: ₹{memory.requested_loan_amount} [{memory.requested_loan_amount_status.upper()}]")
                if memory.requested_loan_type and memory.requested_loan_type_status:
                    lines.append(f"  • Loan Type: {memory.requested_loan_type} [{memory.requested_loan_type_status.upper()}]")
                if memory.requested_tenure_months and memory.requested_tenure_months_status:
                    lines.append(f"  • Tenure: {memory.requested_tenure_months} months [{memory.requested_tenure_months_status.upper()}]")
                # Co-applicant
                if memory.co_applicant_name and memory.co_applicant_name_status:
                    lines.append(f"  • Co-applicant: {memory.co_applicant_name} [{memory.co_applicant_name_status.upper()}]")
                if memory.co_applicant_monthly_income and memory.co_applicant_monthly_income_status:
                    lines.append(f"  • Co-applicant Income: ₹{memory.co_applicant_monthly_income} [{memory.co_applicant_monthly_income_status.upper()}]")
                # Application
                if memory.application_status:
                    lines.append(f"  • Application Status: {memory.application_status.upper()}")
                
                structured_facts = "\n".join(lines) if lines else "No factual data recorded yet."
            else:
                structured_facts = "New customer — no structured data yet."
        except Exception as e:
            logger.error(f"Failed to load SQLite facts for {customer_id}: {e}")
            structured_facts = "[Memory load error — continuing without structured facts]"

        # ---- Tier 2: ChromaDB Semantic Chunks ----
        try:
            relevant_chunks = self.vector_store.search_chunks(
                customer_id=customer_id,
                query_text=current_turn,
                n_results=n_chunks,
            )
        except Exception as e:
            logger.error(f"Failed to search ChromaDB chunks for {customer_id}: {e}")
            relevant_chunks = []

        # ---- Tier 3: Last N Session Summaries ----
        try:
            session_summaries = self.vector_store.get_last_n_summaries(
                customer_id=customer_id,
                n=n_summaries,
            )
        except Exception as e:
            logger.error(f"Failed to retrieve session summaries for {customer_id}: {e}")
            session_summaries = []

        # ---- Assemble Prompt Block ----
        prompt_block = self._format_prompt_block(
            structured_facts=structured_facts,
            relevant_chunks=relevant_chunks,
            session_summaries=session_summaries,
        )

        return {
            "prompt_block": prompt_block,
            "structured_facts": structured_facts,
            "relevant_chunks": relevant_chunks,
            "session_summaries": session_summaries,
            "customer_found": customer_found,
        }

    def _format_prompt_block(
        self,
        structured_facts: str,
        relevant_chunks: List[Dict],
        session_summaries: List[Dict],
    ) -> str:
        """
        Format all 3 tiers into the final injection block.

        This is the exact block injected into the LLM system prompt.
        """
        sections = []

        # --- Section 1: Structured KV Facts ---
        sections.append("WHAT YOU KNOW ABOUT THIS CUSTOMER:")
        sections.append(structured_facts if structured_facts else "  No factual data yet.")
        sections.append("")

        # --- Section 2: Relevant Past Context (semantic chunks) ---
        sections.append("RELEVANT PAST CONTEXT:")
        if relevant_chunks:
            for chunk in relevant_chunks:
                session_id = chunk["metadata"].get("session_id", "?")
                session_date = chunk["metadata"].get("session_date_human", "")
                date_str = f" ({session_date})" if session_date else ""
                topic = chunk["metadata"].get("topic_tag", "")
                topic_str = f" [{topic}]" if topic else ""
                sections.append(
                    f"  – [{session_id}{date_str}]{topic_str} {chunk['document']}"
                )
        else:
            sections.append("  No relevant past context found.")
        sections.append("")

        # --- Section 3: Session Summaries ---
        sections.append("RECENT SESSION SUMMARIES:")
        if session_summaries:
            for summary in session_summaries:
                session_id = summary["metadata"].get("session_id", "?")
                session_date = summary["metadata"].get("session_date_human", "")
                date_str = f" ({session_date})" if session_date else ""
                sections.append(f"  [{session_id}{date_str}] {summary['document']}")
        else:
            sections.append("  No session summaries yet (first session).")

        return "\n".join(sections)

    def get_confirmed_facts_summary(self, customer_id: str) -> str:
        """
        Get a brief summary of only CONFIRMED facts.
        Used for conflict detection — 'what do we know for certain?'

        Returns:
            A concise string listing all confirmed facts, or empty string.
        """
        try:
            memory = self.db.load_customer_memory(customer_id)
            if not memory:
                return ""

            confirmed = []

            # Helper to add confirmed fields
            def _add_if_confirmed(value, label: str, unit: str = "", status: str = "pending"):
                if value and status == "confirmed":
                    val = f"{unit}{value}" if unit else str(value)
                    confirmed.append(f"{label}={val}")

            _add_if_confirmed(memory.monthly_income, "income", "₹", memory.monthly_income_status)
            _add_if_confirmed(memory.annual_income, "annual_income", "₹", memory.annual_income_status)
            _add_if_confirmed(memory.cibil_score, "cibil", "", memory.cibil_score_status)
            _add_if_confirmed(memory.total_existing_emi_monthly, "emi", "₹", memory.total_existing_emi_monthly_status)
            _add_if_confirmed(memory.requested_loan_amount, "loan_amount", "₹", memory.requested_loan_amount_status)
            _add_if_confirmed(memory.requested_loan_type, "loan_type", "", memory.requested_loan_type_status)
            _add_if_confirmed(memory.full_name, "name", "", memory.full_name_status)
            _add_if_confirmed(memory.city, "city", "", memory.city_status)
            _add_if_confirmed(memory.employer_name, "employer", "", memory.employer_name_status)
            _add_if_confirmed(memory.co_applicant_name, "co_applicant", "", memory.co_applicant_name_status)

            return " | ".join(confirmed) if confirmed else ""

        except Exception as e:
            logger.error(f"Failed to get confirmed facts for {customer_id}: {e}")
            return ""

    def close(self):
        """Close DB connection."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

