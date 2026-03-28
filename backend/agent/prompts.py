"""
LangChain Prompt Templates for Agent Nodes.
Centralized, testable prompt management.
"""

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate


# ============================================================================
# DATABASE SCHEMA REFERENCE  (used by field classification prompt)
# ============================================================================

DATABASE_SCHEMA_REFERENCE = """
CUSTOMER MEMORY DATABASE SCHEMA
================================
All customer data is in a single 'customer_memory' table. Use exact field names.

📋 IDENTITY:  full_name | date_of_birth (YYYY-MM-DD) | phone
🏠 ADDRESS:   address | city | state | pincode
💼 EMPLOYMENT: employer_name | job_title | years_at_job
💰 INCOME:    monthly_income | income_type (salaried/self_employed/rental)
📊 CREDIT:    cibil_score (300-900) | total_existing_emi_monthly | number_of_active_loans
🏦 LOAN REQ:  requested_loan_type (home/auto/personal) | requested_loan_amount | requested_tenure_months | loan_purpose
👥 CO-APPL:  coapplicant_name | coapplicant_relation (spouse/sibling/parent) | coapplicant_income
📱 APP:       application_status (incomplete/complete/processing/approved/rejected/on_hold) | documents_submitted

DATE OF BIRTH — normalize any user format to YYYY-MM-DD:
  "5-3-2005" / "5/3/2005" / "05.03.2005" / "March 5 2005" / "5th March 2005" → "2005-03-05"
  Indian convention: DD/MM/YYYY (day first).
  Trigger phrases: "DOB", "date of birth", "born on", "birthday", "birth date".
"""


def get_database_schema_reference() -> str:
    return DATABASE_SCHEMA_REFERENCE.strip()


# ============================================================================
# QUERY REWRITE PROMPT (for context-aware ChromaDB retrieval)
# ============================================================================

QUERY_REWRITE_PROMPT = PromptTemplate.from_template("""You are a search query optimizer for a loan agent's memory retrieval system.

Your task: rewrite the user's message into a compact, keyword-rich retrieval query that will surface the most relevant past facts from a vector database.

RULES:
- Output ONLY the rewritten query — no explanation, no preamble
- Expand pronouns and vague references using the conversation history
- Include relevant domain terms: income, CIBIL, employment, loan amount, EMI, etc.
- If the message is a greeting or small talk with no retrieval value, output: "general customer profile"
- Keep it under 30 words
- Focus on NOUNS and KEY FACTS, not questions

CONVERSATION HISTORY (last few turns):
{conversation_history}

CURRENT USER MESSAGE:
{user_input}

REWRITTEN RETRIEVAL QUERY:""")


# ============================================================================
# ROUTER PROMPT
# ============================================================================

ROUTER_SYSTEM_PROMPT = """You are a conversational router for a loan agent platform.

Memory extraction has already run silently. Your only job: decide HOW to respond.

ROUTING RULES:
  handle_query   → user is ASKING a question that needs a factual answer
                   e.g. "Am I eligible?", "What's my status?", "How much can I borrow?"
  handle_general → everything else: greetings, statements, confirmations, small talk
                   e.g. "Hi", "My income is 50k" (already saved), "Yes that's right"
"""

ROUTER_USER_PROMPT = """Route this customer message.

RECENT CONVERSATION:
{conversation_history}

CUSTOMER SAID: {user_input}

CUSTOMER PROFILE:
{memory_context}

Decision: handle_query or handle_general? Why? Confidence?"""

ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),
    ("human",  ROUTER_USER_PROMPT),
])


# ============================================================================
# QUERY HANDLER PROMPT
# ============================================================================

QUERY_SYSTEM_PROMPT = """You are a helpful loan officer assistant.

Rules:
- Answer using the customer profile and conversation history below.
- NEVER ask for information that is already in the profile.
- If you don't have enough data, say so honestly and offer to help."""

QUERY_HUMAN_PROMPT = """CUSTOMER PROFILE (what we know):
{memory_context}

RECENT CONVERSATION:
{conversation_history}

CUSTOMER'S QUESTION:
{user_input}

Answer clearly and concisely."""

QUERY_ANSWER_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", QUERY_SYSTEM_PROMPT),
    ("human",  QUERY_HUMAN_PROMPT),
])

# Legacy alias (kept for any imports that use it)
QUERY_ANSWER_PROMPT = PromptTemplate.from_template(
    "CUSTOMER PROFILE:\n{memory_context}\n\nCONVERSATION:\n{conversation_history}\n\nQUESTION:\n{user_input}\n\nAnswer:"
)


# ============================================================================
# GENERAL HANDLER PROMPT
# ============================================================================

GENERAL_SYSTEM_PROMPT = """You are a friendly and professional loan officer.

Rules:
- Use the customer profile to personalise your response.
- NEVER ask for information that is already in the profile.
- Acknowledge what the customer said naturally; keep it warm and concise."""

GENERAL_HUMAN_PROMPT = """CUSTOMER PROFILE (what we know):
{memory_context}

RECENT CONVERSATION:
{conversation_history}

CUSTOMER MESSAGE:
{user_input}

Respond naturally."""

GENERAL_RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", GENERAL_SYSTEM_PROMPT),
    ("human",  GENERAL_HUMAN_PROMPT),
])


# ============================================================================
# MISMATCH CONFIRMATION PROMPT
# ============================================================================

MISMATCH_VERIFICATION_SYSTEM_PROMPT = """You are a polite, empathetic customer service rep for a loan platform.

Task: Tell the customer we noticed a discrepancy and ask them to confirm which value is correct.
Tone: warm, professional, non-accusatory.

Steps:
1. Name the conflicting field(s) clearly — old value vs new value.
2. Mention when the old value was recorded if available.
3. Ask which is correct.
4. Explain briefly why accuracy matters for their loan assessment."""

MISMATCH_VERIFICATION_USER_PROMPT = """CONFLICTING INFORMATION:
{mismatch_details}

WHEN OLD INFO WAS RECORDED:
{historical_context}

CUSTOMER PROFILE:
{customer_profile}

Write the confirmation message."""

MISMATCH_VERIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", MISMATCH_VERIFICATION_SYSTEM_PROMPT),
    ("human",  MISMATCH_VERIFICATION_USER_PROMPT),
])


# ============================================================================
# FIELD CLASSIFICATION PROMPT
# ============================================================================

FIELD_CLASSIFICATION_SYSTEM_PROMPT = f"""You are a data classification system for a loan platform.

Classify each piece of information in the customer statement:
  SCHEMA_FIELD    → maps to a column in the database (use exact field name)
  CONTEXTUAL_INFO → useful info that doesn't fit any schema column

DATABASE SCHEMA:
{DATABASE_SCHEMA_REFERENCE}

RULES:
- Extract EVERYTHING mentioned — leave nothing behind.
- Use conversation history to resolve short answers / pronouns.
- For date_of_birth: normalized_value MUST be YYYY-MM-DD regardless of input format.
- is_correction = true ONLY when user explicitly corrects a previously stated value.
"""

FIELD_CLASSIFICATION_USER_PROMPT = """CUSTOMER PROFILE (already known — do NOT re-extract these):
{memory_context}

RECENT CONVERSATION:
{conversation_history}

CUSTOMER STATEMENT:
"{user_input}"

Classify every new piece of information. For each item provide:
  raw_value       – exact words from the customer
  field_type      – "SCHEMA_FIELD" or "CONTEXTUAL_INFO"
  field_name      – DB column name (SCHEMA_FIELD) or short label (CONTEXTUAL_INFO)
  normalized_value – cleaned value ready for storage
  category        – personal | income | employment | loan | credit | other
  is_correction   – true if explicitly correcting a previous value, else false"""

FIELD_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", FIELD_CLASSIFICATION_SYSTEM_PROMPT),
    ("human",  FIELD_CLASSIFICATION_USER_PROMPT),
])


# ============================================================================
# MISC CONSTANTS
# ============================================================================

MEMORY_UPDATE_ACKNOWLEDGMENT = (
    "Thank you! I've updated your profile — that'll help us assess your loan eligibility accurately."
)

MEMORY_CONFLICT_TEMPLATE = """I noticed some differences in your information:

{conflicts}

Could you confirm which values are correct? Accurate details are important for your loan assessment."""
