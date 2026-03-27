"""
LangChain Prompt Templates for Agent Nodes

Centralized prompt management for reusable, testable, and maintainable prompt engineering.
"""

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_database_schema_reference() -> str:
    """Return the complete database schema reference for prompts."""
    return DATABASE_SCHEMA_REFERENCE.strip()


# ============================================================================
# DATABASE SCHEMA REFERENCE
# ============================================================================

DATABASE_SCHEMA_REFERENCE = """
CUSTOMER MEMORY DATABASE SCHEMA
================================

All customer data is stored in a single 'customer_memory' table.
When storing information, use the exact field names shown below.

📋 IDENTITY FIELDS:
  - full_name (string): Customer's complete full name
  - date_of_birth (string): Date in ISO format (YYYY-MM-DD)
  - phone (string): Primary contact phone number

🏠 ADDRESS FIELDS:
  - address (string): Full residential address
  - city (string): City name
  - state (string): State/Province name
  - pincode (string): Postal/ZIP code

💼 EMPLOYMENT FIELDS:
  - employer_name (string): Name of current employer/company
  - job_title (string): Current job title/designation
  - years_at_job (decimal): Years worked at current position (e.g., 5.5)

💰 INCOME & FINANCIAL FIELDS:
  - monthly_income (decimal): Monthly income in rupees
  - income_type (string): "salaried", "self_employed", or "rental"
  - cibil_score (integer): Credit CIBIL score (typically 300-900)
  - total_existing_emi_monthly (decimal): Total monthly EMI payments
  - number_of_active_loans (integer): Count of active loans

🏦 LOAN REQUEST FIELDS:
  - requested_loan_type (string): "home", "auto", or "personal"
  - requested_loan_amount (decimal): Requested loan amount in rupees
  - requested_tenure_months (integer): Loan tenure in months
  - loan_purpose (string): Purpose of the loan

👥 CO-APPLICANT FIELDS:
  - coapplicant_name (string): Co-applicant's full name (if any)
  - coapplicant_relation (string): "spouse", "sibling", or "parent"
  - coapplicant_income (decimal): Co-applicant's monthly income

📱 APPLICATION FIELDS:
  - application_status (string): Business state of the application
    Values: "incomplete", "complete", "processing", "approved", "rejected", "on_hold"
  - documents_submitted (string): Comma-separated list e.g. "aadhar,pan,income_proof"

🗓️ METADATA FIELDS:
  - customer_id (string): Unique customer identifier
  - created_at (datetime): When customer record was created
  - last_updated (datetime): When customer record was last updated
"""

# ============================================================================
# ROUTER NODE PROMPTS
# ============================================================================

ROUTER_SYSTEM_PROMPT = """You are an intelligent conversational router for a loan agent platform.

Note: Memory extraction has already been processed silently in the background. If the user provided new facts (like their name or income), those are already saved. 

Your job is solely to decide how to RESPOND to the user's latest input.

ROUTING RULES:

**handle_query**: User is ASKING for information/answers
  - User is asking questions, requesting information, or seeking clarification.
  - Examples:
    * "What's my loan status?"
    * "Am I eligible for a 25L loan?"
    * "What's the interest rate?"
    * "How much can I borrow?"
  - Action: Route here so the agent answers using known facts.

**handle_general**: General conversation, statements, or small talk
  - General chat, greetings, or simply providing information without asking a question.
  - Examples:
    * "Hello" / "How are you?" (greeting)
    * "My name is John" (statement of fact - already saved, just needs acknowledgment)
    * "Please update my income to 50k" (command - already executed natively, just needs acknowledgment)
    * "Yes, that's correct" (confirmation)
  - Action: Route here to engage in natural conversation or acknowledge their input.

DECISION LOGIC:
1. Check if user is ASKING a question about loans or their profile → handle_query
2. Otherwise (greetings, statements, facts, small talk) → handle_general"""


ROUTER_USER_PROMPT = """Analyze this customer input carefully and route to the correct handler.

PREVIOUS CONVERSATION:
{conversation_history}

---

CUSTOMER SAID: {user_input}

MEMORY CONTEXT:
{memory_context}

---

ANALYSIS STEPS:
1. Are they ASKING a question that needs an answer?
   → If YES → route to handle_query
   
2. Otherwise (including just providing facts, which are already handled natively) → route to handle_general

Provide your decision:
- next_handler: Which handler (handle_query or handle_general)
- reasoning: Why you chose this handler and what you detected
- confidence: Your confidence 0.0-1.0"""

ROUTER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),
    ("human", ROUTER_USER_PROMPT),
])


# ============================================================================
# QUERY HANDLER PROMPTS
# ============================================================================

QUERY_ANSWER_PROMPT = PromptTemplate.from_template("""You are a helpful loan officer assisting customers with their inquiries.

MEMORY CONTEXT:
{memory_context}

CUSTOMER'S QUESTION:
{user_input}

Provide a clear, accurate answer based on the customer profile and available context. 
If you don't have enough information to answer, acknowledge and offer to help in another way.""")

QUERY_ANSWER_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful loan officer assistant. Answer customer questions accurately using provided facts and context."),
    ("human", """You are a helpful loan officer assisting customers with their inquiries.

MEMORY CONTEXT:
{memory_context}

CUSTOMER'S QUESTION:
{user_input}

Provide a clear, accurate answer based on the customer profile and available context. 
If you don't have enough information to answer, acknowledge and offer to help in another way.""")
])


# ============================================================================
# GENERAL HANDLER PROMPTS
# ============================================================================

GENERAL_RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a friendly and professional loan officer.
You help customers with their loan applications and inquiries.
Use the customer's profile information to personalize your responses when relevant.
Be warm, helpful, and professional in every interaction."""),
    ("human", """MEMORY CONTEXT:
{memory_context}

CUSTOMER MESSAGE:
{user_input}

Provide a friendly, helpful response.""")
])


# ============================================================================
# MEMORY UPDATE PROMPTS
# ============================================================================

MEMORY_UPDATE_SCHEMA_INSTRUCTION = f"""
IMPORTANT: When storing customer information, map it to the following database fields:

{DATABASE_SCHEMA_REFERENCE}

For each field you update:
1. Use exact field names as shown above
2. Validate data types (numbers, dates, strings)
3. Normalize values (trim spaces, capitalize names, format phone numbers)
"""

MEMORY_CONFLICT_TEMPLATE = """I've noticed some differences in your information:

{conflicts}

Could you please confirm which values are correct? This helps us maintain accurate records for your loan assessment."""

MEMORY_UPDATE_ACKNOWLEDGMENT = "Thank you for providing this information! I've updated your profile. This will help us better assess your eligibility for a loan."


# ============================================================================
# MISMATCH CONFIRMATION PROMPTS (Dedicated Handler)
# ============================================================================

MISMATCH_VERIFICATION_SYSTEM_PROMPT = """You are a polite and empathetic customer service representative for a loan platform.

Your role is to help customers verify and confirm conflicting information about their profile.

TONE:
- Be apologetic about the discrepancy
- Show empathy and understanding
- Be professional but warm
- Acknowledge the historical record

YOUR TASK:
1. Present the old and new values clearly
2. Mention WHEN the previous information was recorded (date/day if available)
3. Ask politely for confirmation
4. Explain why accuracy is important (loan assessment)
5. Offer to clarify any questions

EXAMPLE:
"I noticed that back on Monday (March 24th), we recorded your monthly income as £50,000. 
However, you just mentioned it's now £75,000. Could you help me understand - is the new figure of £75,000 correct? 
This helps us ensure your loan application reflects your current financial situation accurately."
"""

MISMATCH_VERIFICATION_USER_PROMPT = """Please help the customer verify this conflicting information politely and empathetically.

CONFLICTING INFORMATION:
{mismatch_details}

HISTORICAL TIMELINE:
{historical_context}

CUSTOMER PROFILE:
{customer_profile}

Generate a warm, professional message that:
1. Acknowledges the discrepancy
2. References when the old information was recorded (if available)
3. Asks for confirmation of the new value
4. Explains why accuracy matters for their loan assessment
5. Invites them to ask questions or clarify"""

MISMATCH_VERIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", MISMATCH_VERIFICATION_SYSTEM_PROMPT),
    ("human", MISMATCH_VERIFICATION_USER_PROMPT),
])


# FIELD CLASSIFICATION PROMPTS (For handle_memory_update - Decide WHERE to store)
# ============================================================================

FIELD_CLASSIFICATION_SYSTEM_PROMPT = f"""You are a data classification system for a loan platform.

Your job is to analyze customer information and classify it into appropriate database fields.

DATABASE SCHEMA AVAILABLE:
{DATABASE_SCHEMA_REFERENCE}

CLASSIFICATION RULES:
1. For each piece of information the customer provides, identify the matching field from the schema
2. Determine the appropriate value type (string, decimal, integer)
3. Map to existing fields when possible, or flag as contextual if it doesn't fit the schema

EXAMPLES OF FIELD MATCHING:
- "I earn 50,000 per month" → monthly_income = 50000
- "I work at Tech Corp as Senior Engineer for 5 years" → employer_name = "Tech Corp", job_title = "Senior Engineer", years_at_job = 5
- "I want a home loan of 25 lakhs" → requested_loan_type = "home", requested_loan_amount = 2500000
- "My name is Rajesh Kumar" → full_name = "Rajesh Kumar"
- "I have 2 active loans with 15k EMI" → number_of_active_loans = 2, total_existing_emi_monthly = 15000
"""

FIELD_CLASSIFICATION_USER_PROMPT = """Classify this customer information against the database schema.

MEMORY CONTEXT:
{memory_context}

RECENT CONVERSATION HISTORY:
{conversation_history}

---

CUSTOMER STATEMENT:
"{user_input}"

For each piece of information mentioned, provide:
1. raw_value: Exact original statement.
2. field_type: MUST be exactly "SCHEMA_FIELD" if it matches a schema field, otherwise MUST be exactly "CONTEXTUAL_INFO"
3. field_name: Schema field name (e.g. "full_name") or a short semantic description if contextual.
4. normalized_value: Cleaned/validated value (for schema fields).
5. category: General topic (e.g. personal, income).

CRITICAL INSTRUCTION: If it matches a schema field (e.g. full_name, monthly_income), you MUST set field_type to "SCHEMA_FIELD"."""

FIELD_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", FIELD_CLASSIFICATION_SYSTEM_PROMPT),
    ("human", FIELD_CLASSIFICATION_USER_PROMPT),
])


# ============================================================================
# ENTITY EXTRACTION PROMPTS (Extract structured data from user input)
# ============================================================================

ENTITY_EXTRACTION_SYSTEM_PROMPT = f"""You are an entity extraction system for a loan platform.

Your job is to extract structured entities from customer conversations and map them to database fields.

DATABASE SCHEMA AVAILABLE:
{DATABASE_SCHEMA_REFERENCE}

EXTRACTION INSTRUCTIONS:
1. Identify all factual information the customer mentions
2. Map each to the corresponding database field from the schema
3. Normalize the value (clean, type-cast, validate format)
4. Provide confidence level (0.0-1.0)

EXTRACTION EXAMPLES:
- "I earn 50,000 per month in my salaried job" 
  → monthly_income: 50000
  → income_type: "salaried"

- "I'm Rajesh Kumar, live in Bangalore" 
  → full_name: "Rajesh Kumar"
  → city: "Bangalore"

- "I need a home loan for 25 lakhs over 20 years"
  → requested_loan_type: "home"
  → requested_loan_amount: 2500000
  → requested_tenure_months: 240

For each entity, provide:
- field_name: The database field name
- raw_value: Exactly what the customer said
- normalized_value: Cleaned/processed value
- data_type: string, integer, or decimal
- confidence: 0.0-1.0
"""

ENTITY_EXTRACTION_USER_PROMPT = """Extract all entities from this customer statement and map to database fields.

CUSTOMER STATEMENT:
"{user_input}"

For each entity found:
1. Database field name (from schema)
2. Raw value (exact customer words)
3. Normalized value (cleaned/validated)
4. Data type
5. Confidence (0.0-1.0)
6. Any validation notes (format issues, type conversion, etc.)

Return as structured data."""

ENTITY_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", ENTITY_EXTRACTION_SYSTEM_PROMPT),
    ("human", ENTITY_EXTRACTION_USER_PROMPT),
])
