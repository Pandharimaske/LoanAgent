"""
LangChain Tool definitions for the LoanAgent.

Tools registered here are available to the agent's handle_query node.
Each tool is a pure function decorated with @tool — the agent decides
whether to call it based on the user's question.

Current tools:
  search_loan_products  — semantic search over bank loan product knowledge base
                          (rates, eligibility, documents, FAQs, govt schemes)
"""

import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.tools import tool
from memory.loan_knowledge_store import LoanKnowledgeStore

logger = logging.getLogger(__name__)

# Singleton — one store instance reused across tool calls (avoids repeated ChromaDB opens)
_loan_store: Optional[LoanKnowledgeStore] = None


def _get_loan_store() -> LoanKnowledgeStore:
    global _loan_store
    if _loan_store is None:
        _loan_store = LoanKnowledgeStore()
    return _loan_store


# =============================================================================
# TOOL: search_loan_products
# =============================================================================

@tool
def search_loan_products(query: str) -> str:
    """
    Search the bank's loan product knowledge base for information about:
    - Loan types offered (Home, Personal, Business/MSME, Agriculture, Education, Gold)
    - Interest rates and rate slabs by CIBIL score
    - Eligibility criteria: age, income, CIBIL score, employment, FOIR limits
    - Required documents for each loan type
    - EMI calculations and tenure options
    - Processing fees and prepayment charges
    - Government schemes linked to each product (PMAY, MUDRA, KCC, CSIS etc.)
    - Special concessions (women borrowers, existing customers, green buildings)
    - Frequently asked questions about each loan product

    Use this tool whenever the customer asks about loan products, rates, eligibility,
    documents required, or any bank product-specific information.

    Args:
        query: A natural language question or keyword phrase about loan products.
               Examples:
               - "home loan interest rate for CIBIL 750"
               - "documents required for education loan abroad"
               - "MSME business loan eligibility 2 years vintage"
               - "gold loan LTV ratio and disbursal time"
               - "agriculture KCC loan effective interest rate"

    Returns:
        Relevant loan product information as formatted text.
        Returns 'No relevant loan product information found.' if nothing matches.
    """
    try:
        store = _get_loan_store()

        if store.count() == 0:
            logger.warning("Loan knowledge base is empty — ingest_loan_data.py not run yet")
            return (
                "The loan product knowledge base is not yet populated. "
                "Please run scripts/ingest_loan_data.py to load product data."
            )

        result = store.format_for_prompt(query=query, n_results=4)

        if not result:
            return "No relevant loan product information found for your query."

        logger.info(f"search_loan_products: '{query[:60]}' → {len(result)} chars retrieved")
        return result

    except Exception as e:
        logger.error(f"search_loan_products tool failed: {e}", exc_info=True)
        return f"Loan product search encountered an error: {str(e)}"


# =============================================================================
# TOOL REGISTRY — add new tools here as the agent grows
# =============================================================================

ALL_TOOLS = [
    search_loan_products,
]

TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}


def get_tool(name: str):
    """Retrieve a registered tool by name."""
    return TOOLS_BY_NAME.get(name)
