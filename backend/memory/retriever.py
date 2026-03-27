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

from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import (
    CustomerMemoryNonPII,
    CustomerMemoryPII,
    FixedEntity,
    MemoryStatus,
    ApplicationStatus,
)
from config import VECTOR_SEARCH_TOP_K

logger = logging.getLogger(__name__)


# ============================================================================
# FACT FORMATTER — Turns SQLite models into human-readable strings
# ============================================================================


def _fmt_entity(entity: Optional[FixedEntity], label: str, unit: str = "") -> Optional[str]:
    """
    Format a single FixedEntity into a readable fact line.
    Only returns a value if status is CONFIRMED or PENDING.
    Skips RETRACTED and SUPERSEDED.

    Example:
        "Monthly Income: ₹45,000 [CONFIRMED, Session S1]"
        "CIBIL Score: 750 [PENDING]"
    """
    if entity is None or entity.current is None:
        return None

    rec = entity.current
    if rec.status in (MemoryStatus.RETRACTED, MemoryStatus.SUPERSEDED):
        return None

    value = rec.value
    if unit:
        formatted_value = f"{unit}{value}"
    else:
        formatted_value = str(value)

    status_tag = f"[{rec.status.value.upper()}, Session {rec.session_id}]"
    return f"{label}: {formatted_value} {status_tag}"


def _fmt_currency(entity: Optional[FixedEntity], label: str) -> Optional[str]:
    """Format a currency FixedEntity with rupee symbol."""
    return _fmt_entity(entity, label, unit="₹")


def build_nonpii_facts(nonpii: CustomerMemoryNonPII) -> str:
    """
    Build the structured fact block from Non-PII SQLite data.
    Only includes fields that have a current value (CONFIRMED or PENDING).
    """
    lines = []

    # Income & Employment
    income_line = _fmt_currency(nonpii.monthly_income, "Monthly Income")
    if income_line:
        lines.append(income_line)

    income_type = _fmt_entity(nonpii.income_type, "Income Type")
    if income_type:
        lines.append(income_type)

    exp = _fmt_entity(nonpii.total_work_experience_years, "Work Experience")
    if exp:
        lines.append(exp + " years")

    # Credit
    cibil = _fmt_entity(nonpii.cibil_score, "CIBIL Score")
    if cibil:
        lines.append(cibil)

    emi = _fmt_currency(nonpii.total_existing_emi_monthly, "Existing EMI (monthly)")
    if emi:
        lines.append(emi)

    loans = _fmt_entity(nonpii.number_of_active_loans, "Active Loans")
    if loans:
        lines.append(loans)

    # Loan Request
    if nonpii.loan_request:
        lr = nonpii.loan_request
        loan_type = _fmt_entity(lr.loan_type, "Loan Type")
        if loan_type:
            lines.append(loan_type)

        loan_amt = _fmt_currency(lr.loan_amount, "Loan Amount Requested")
        if loan_amt:
            lines.append(loan_amt)

        tenure = _fmt_entity(lr.tenure_months, "Tenure")
        if tenure:
            lines.append(tenure + " months")

        purpose = _fmt_entity(lr.purpose, "Loan Purpose")
        if purpose:
            lines.append(purpose)

    # Documents
    if nonpii.documents_submitted:
        doc_names = [d.doc_type for d in nonpii.documents_submitted]
        lines.append(f"Documents Submitted: {', '.join(doc_names)}")

    # Application status
    if nonpii.application_status != ApplicationStatus.INCOMPLETE:
        lines.append(f"Application Status: {nonpii.application_status.value.upper()}")

    if not lines:
        return "No factual data recorded yet."

    return "\n".join(f"  • {line}" for line in lines)


def build_pii_facts(pii: CustomerMemoryPII) -> str:
    """
    Build the PII fact block from encrypted SQLite data.
    Includes name, contact, co-applicants, guarantors.
    """
    lines = []

    # Identity
    name = _fmt_entity(pii.full_name, "Customer Name")
    if name:
        lines.append(name)

    phone = _fmt_entity(pii.primary_phone, "Phone")
    if phone:
        lines.append(phone)

    city = _fmt_entity(pii.city, "City")
    if city:
        lines.append(city)

    state = _fmt_entity(pii.state, "State")
    if state:
        lines.append(state)

    # Employment
    employer = _fmt_entity(pii.employer_name, "Employer")
    if employer:
        lines.append(employer)

    years_job = _fmt_entity(pii.years_at_current_job, "Years at Current Job")
    if years_job:
        lines.append(years_job)

    # Co-applicants
    for i, co in enumerate(pii.co_applicants, 1):
        co_parts = []
        if co.name and co.name.current:
            co_parts.append(co.name.current.value)
        if co.relation and co.relation.current:
            co_parts.append(f"({co.relation.current.value})")
        if co.income_monthly and co.income_monthly.current:
            co_parts.append(f"income ₹{co.income_monthly.current.value}")
        if co_parts:
            status_tag = ""
            if co.name and co.name.current:
                status_tag = f" [{co.name.current.status.value.upper()}]"
            lines.append(f"Co-applicant {i}: {' '.join(co_parts)}{status_tag}")

    # Guarantors
    for i, g in enumerate(pii.guarantors, 1):
        g_parts = []
        if g.name and g.name.current:
            g_parts.append(g.name.current.value)
        if g.relation and g.relation.current:
            g_parts.append(f"({g.relation.current.value})")
        if g_parts:
            lines.append(f"Guarantor {i}: {' '.join(g_parts)}")

    if not lines:
        return "No personal information recorded yet."

    return "\n".join(f"  • {line}" for line in lines)


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
        include_pii: bool = True,
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
            nonpii, pii = self.db.load_customer_memory(customer_id)
            if nonpii:
                customer_found = True
                fact_lines = build_nonpii_facts(nonpii)
                if pii and include_pii:
                    pii_lines = build_pii_facts(pii)
                    structured_facts = f"{pii_lines}\n{fact_lines}"
                else:
                    structured_facts = fact_lines
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
            nonpii, pii = self.db.load_customer_memory(customer_id)
            if not nonpii:
                return ""

            confirmed = []

            def _check(entity: Optional[FixedEntity], label: str, unit: str = ""):
                if entity and entity.current:
                    if entity.current.status == MemoryStatus.CONFIRMED:
                        val = f"{unit}{entity.current.value}"
                        confirmed.append(f"{label}={val}")

            _check(nonpii.monthly_income, "income", "₹")
            _check(nonpii.income_type, "income_type")
            _check(nonpii.cibil_score, "cibil")
            _check(nonpii.total_existing_emi_monthly, "emi", "₹")

            if nonpii.loan_request:
                _check(nonpii.loan_request.loan_amount, "loan_amount", "₹")
                _check(nonpii.loan_request.loan_type, "loan_type")

            if pii:
                _check(pii.full_name, "name")
                _check(pii.city, "city")
                _check(pii.employer_name, "employer")
                for i, co in enumerate(pii.co_applicants, 1):
                    if co.name and co.name.current:
                        if co.name.current.status == MemoryStatus.CONFIRMED:
                            confirmed.append(f"co_applicant_{i}={co.name.current.value}")

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


# ============================================================================
# QUICK TEST
# ============================================================================

if __name__ == "__main__":
    import tempfile, os

    print("=" * 65)
    print("MemoryRetriever Test")
    print("=" * 65)

    # Set up temp stores
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test_memory.db")
    chroma_path = os.path.join(tmp, "chroma")

    db = MemoryDatabase(db_path=db_path)
    db.connect()
    db.init_schema()

    vector = VectorStore(persist_path=chroma_path)

    # Seed SQLite with Rajesh's data
    from memory.models import create_test_memory, SessionLog
    nonpii, pii = create_test_memory()
    db.save_customer_memory(nonpii, pii)

    # Seed a session
    session = SessionLog(
        session_id="S1",
        customer_id="RAJESH_001",
        started_at=datetime.now(),
        agent_id="AGENT_A",
    )
    db.save_session(session)
    db.end_session("S1", summary="Rajesh needs home loan. Income 45000. Wife Sunita co-applicant.")

    # Seed ChromaDB
    vector.add_session_summary(
        customer_id="RAJESH_001",
        session_id="S1",
        summary_text="Rajesh applied for home loan. Monthly income 45000. Wife Sunita as co-applicant.",
        session_date="Monday Jan 15",
        agent_id="AGENT_A",
    )
    vector.add_chunk(
        customer_id="RAJESH_001",
        session_id="S1",
        text="Rajesh mentioned income is 45000 per month",
        topic_tag="income",
        turn_index=1,
    )
    vector.add_chunk(
        customer_id="RAJESH_001",
        session_id="S1",
        text="Wife Sunita Kumar will be co-applicant for the home loan",
        topic_tag="co_applicant",
        turn_index=2,
    )

    # Build context
    retriever = MemoryRetriever(db=db, vector_store=vector)

    print("\n--- build_context() for turn: 'what is my income?' ---\n")
    result = retriever.build_context(
        customer_id="RAJESH_001",
        current_turn="what is my income?",
    )
    print(result["prompt_block"])

    print("\n--- Confirmed facts summary ---")
    print(retriever.get_confirmed_facts_summary("RAJESH_001"))

    print("\n--- Non-existent customer ---")
    result2 = retriever.build_context(
        customer_id="UNKNOWN_999",
        current_turn="hello",
    )
    print(f"customer_found: {result2['customer_found']}")
    print(result2["prompt_block"][:200])

    db.close()
    print("\n[ALL TESTS PASSED]")
    print("=" * 65)
