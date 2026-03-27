"""
Handler nodes for different types of customer interactions.

Handlers:
- handle_memory_update: Store new customer information (schema + contextual)
- handle_mismatch_confirmation: Ask user to verify conflicting data
- handle_query: Answer customer questions about their loan/profile
- handle_general: General conversation with context injection
"""

import sys
import logging
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import (
    MEMORY_UPDATE_ACKNOWLEDGMENT,
    QUERY_ANSWER_CHAT_PROMPT,
    GENERAL_RESPONSE_PROMPT,
    MISMATCH_VERIFICATION_PROMPT,
)
from agent.schemas import SchemaFieldValidator
from agent.helpers import classify_fields_with_llm, create_llm
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import FixedEntity, MemoryStatus, CustomerMemoryNonPII, CustomerMemoryPII
from config import SQLITE_PATH, CHROMA_PATH

logger = logging.getLogger(__name__)


# ============================================================================
# HANDLER 1: HANDLE_MEMORY_UPDATE
# ============================================================================

async def handle_memory_update(state: SessionState) -> SessionState:
    """
    Handle when user provided NEW information (no conflicts).
    
    Flow:
    1. Classify fields: Is this a schema field or contextual info?
    2. Validate: If schema field, validate data types and ranges using Pydantic
    3. Store: 
       - Schema fields → SQLite (with FixedEntity, status=CONFIRMED)
       - Contextual → ChromaDB (semantic embeddings + metadata)
    4. Respond: Acknowledge and thank user
    
    Metadata added: session_id, timestamp, source, customer_id, confidence
    """
    try:
        user_input = state.get("user_input", "")
        customer_id = state.get("customer_id", "")
        session_id = state.get("session_id", "")
        
        if not user_input or not customer_id:
            state["agent_response"] = "I couldn't process this information. Please try again."
            return state
        
        logger.info("📝 Memory Update Handler (New Info):")
        logger.info(f"   User Input: {user_input[:100]}...")
        
        # ====================================================================
        # STEP 1: CLASSIFY FIELDS (LLM decides WHERE to store)
        # ====================================================================
        logger.info("🏷️  Step 1: Classifying fields...")
        classifications = await classify_fields_with_llm(user_input)
        
        schema_fields = {}
        contextual_info = {}
        
        for field_name, classification in classifications.items():
            if classification.field_type == "SCHEMA_FIELD":
                schema_fields[field_name] = classification
            else:
                contextual_info[field_name] = classification
        
        logger.info(f"   Schema fields: {len(schema_fields)} | Contextual: {len(contextual_info)}")
        
        # ====================================================================
        # STEP 2: VALIDATE SCHEMA FIELDS (using Pydantic model)
        # ====================================================================
        valid_schema_fields = {}
        failed_validations = []
        
        for field_name, classification in schema_fields.items():
            logger.debug(f"   Validating {field_name}...")
            try:
                # Create validator with field data - Pydantic validates automatically
                validator_data = {field_name: classification.normalized_value}
                validator = SchemaFieldValidator(**validator_data)
                
                # Get the validated/coerced value using model_dump()
                validated_dict = validator.model_dump(exclude_none=True)
                normalized_value = validated_dict[field_name]
                
                valid_schema_fields[field_name] = {
                    "field_name": field_name,
                    "value": normalized_value,
                    "original": classification.raw_value,
                    "confidence": classification.confidence,
                }
                logger.debug(f"      ✅ Valid: {normalized_value}")
                
            except Exception as e:
                failed_validations.append((field_name, str(e)))
                logger.warning(f"      ❌ Invalid: {str(e)}")
        
        # ====================================================================
        # STEP 3a: STORE SCHEMA FIELDS IN SQLITE (BOTH PII & NON-PII)
        # ====================================================================
        if valid_schema_fields:
            logger.info(f"💾 Storing {len(valid_schema_fields)} fields in SQLite...")
            db = MemoryDatabase(db_path=SQLITE_PATH)
            db.connect()
            
            try:
                # Load existing customer memory (returns tuple: nonpii, pii)
                nonpii, pii = db.load_customer_memory(customer_id)
                
                # If no existing memory, create new objects
                if not nonpii:
                    nonpii = CustomerMemoryNonPII(
                        customer_id=customer_id,
                        created_at=datetime.now(),
                        last_updated=datetime.now(),
                    )
                
                if not pii:
                    pii = CustomerMemoryPII(
                        customer_id=customer_id,
                        created_at=datetime.now(),
                        last_updated=datetime.now(),
                    )
                
                # ====================================================================
                # Map fields to PII vs NonPII
                # ====================================================================
                pii_fields = {
                    'full_name', 'date_of_birth', 'gender', 'marital_status',
                    'primary_phone', 'current_address', 'city', 'state', 'pincode',
                    'employer_name', 'years_at_current_job'
                }
                
                # Update each field (to appropriate table)
                for field_name, field_data in valid_schema_fields.items():
                    entity = FixedEntity()
                    entity.add_value(
                        value=field_data["value"],
                        session_id=session_id,
                        status=MemoryStatus.CONFIRMED,
                    )
                    entity.confirm()
                    
                    if field_name in pii_fields:
                        # Save to PII table (will be encrypted)
                        if hasattr(pii, field_name):
                            setattr(pii, field_name, entity)
                            logger.info(f"      ✅ {field_name} → PII (encrypted)")
                    else:
                        # Save to NonPII table (plaintext)
                        if hasattr(nonpii, field_name):
                            setattr(nonpii, field_name, entity)
                            logger.info(f"      ✅ {field_name} → NonPII (plaintext)")
                
                nonpii.last_updated = datetime.now()
                pii.last_updated = datetime.now()
                
                # Save both tables to SQLite
                db.save_customer_memory(nonpii, pii)
                logger.info("✅ SQLite update complete (PII encrypted, NonPII plaintext)")
                
            except Exception as e:
                logger.error(f"❌ SQLite storage failed: {e}")
            finally:
                db.close()
        
        # ====================================================================
        # STEP 3b: STORE CONTEXTUAL INFO IN CHROMADB
        # ====================================================================
        if contextual_info:
            logger.info(f"🔍 Storing {len(contextual_info)} contextual items in ChromaDB...")
            vs = VectorStore(persist_path=CHROMA_PATH)
            
            try:
                for field_name, classification in contextual_info.items():
                    # Format semantic chunk
                    chunk_text = f"{classification.field_name}: {classification.raw_value}"
                    
                    metadata = {
                        "type": "memory_update",
                        "category": classification.category,
                        "customer_id": customer_id,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                        "source": "handle_memory_update",
                        "confidence": str(classification.confidence),
                        "original_text": classification.raw_value,
                    }
                    
                    # Add to ChromaDB
                    vs.add_chunk(
                        customer_id=customer_id,
                        text=chunk_text,
                        metadata=metadata,
                        topic_tag=classification.category,
                    )
                    logger.info(f"      ✅ {classification.category}: {chunk_text}")
                
                logger.info("✅ ChromaDB update complete")
                
            except Exception as e:
                logger.error(f"❌ ChromaDB storage failed: {e}")
        
        # ====================================================================
        # STEP 4: GENERATE RESPONSE
        # ====================================================================
        update_summary = []
        if valid_schema_fields:
            fields_list = ", ".join(valid_schema_fields.keys())
            update_summary.append(f"updated {len(valid_schema_fields)} profile fields ({fields_list})")
        
        if contextual_info:
            update_summary.append(f"noted {len(contextual_info)} preferences/details")
        
        if failed_validations:
            logger.warning(f"⚠️  Failed validations: {len(failed_validations)}")
        
        response = MEMORY_UPDATE_ACKNOWLEDGMENT
        if update_summary:
            response += f" I've {' and '.join(update_summary)}."
        
        state["agent_response"] = response
        state["memory_updates"] = [
            {"field": name, "value": data["value"], "type": "schema"} 
            for name, data in valid_schema_fields.items()
        ] + [
            {"field": name, "value": classification.raw_value, "type": "contextual"} 
            for name, classification in contextual_info.items()
        ]
        
        logger.info(f"✅ Memory update complete: {len(state['memory_updates'])} items processed")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Memory update handler failed: {e}", exc_info=True)
        state["agent_response"] = "I encountered an error storing this information. Please try again."
        return state


# ============================================================================
# HANDLER 2: HANDLE_MISMATCH_CONFIRMATION
# ============================================================================

async def handle_mismatch_confirmation(state: SessionState) -> SessionState:
    """
    Handle when user provided CONFLICTING information.
    
    Politely asks the user to verify/confirm the new value while mentioning
    WHEN the previous information was recorded.
    
    Router has already identified:
    1. has_mismatch: True (there are conflicts)
    2. mismatched_fields: {field: {old_value, new_value, ...}}
    3. dynamic_context: Historical info from ChromaDB (may contain timestamps)
    """
    try:
        mismatches = state.get("mismatched_fields", {})
        dynamic_context = state.get("dynamic_context", [])
        confirmed_facts = state.get("confirmed_facts", {})
        
        logger.info("🔍 Mismatch Confirmation Handler:")
        logger.info(f"   Conflicts Found: {len(mismatches)}")
        logger.info(f"   Fields: {list(mismatches.keys())}")
        
        if not mismatches:
            # Fallback if no mismatches despite being routed here
            state["agent_response"] = MEMORY_UPDATE_ACKNOWLEDGMENT
            logger.warning("⚠️  No mismatches found despite routing to mismatch handler")
            return state
        
        # ====================================================================
        # BUILD MISMATCH DETAILS WITH EXPLANATIONS FROM LLM
        # ====================================================================
        mismatch_details_parts = []
        for field, conflict_info in mismatches.items():
            old_val = conflict_info.get("old_value", "unknown")
            new_val = conflict_info.get("new_value", "unknown")
            confidence = conflict_info.get("confidence", 0.0)
            explanation = conflict_info.get("explanation", "Data changed")
            
            detail = f"• {field.replace('_', ' ').title()}\n"
            detail += f"  Previous: {old_val}\n"
            detail += f"  Current: {new_val}\n"
            detail += f"  Status: {explanation}\n"
            detail += f"  Confidence: {confidence:.0%}"
            
            mismatch_details_parts.append(detail)
        
        mismatch_details = "\n\n".join(mismatch_details_parts)
        
        # ====================================================================
        # BUILD HISTORICAL CONTEXT (hint at when old data was recorded)
        # ====================================================================
        # Try to extract timeline info from ChromaDB results
        historical_context = "Unknown date"
        
        if dynamic_context:
            # Look for date/time references in context
            context_text = " ".join(dynamic_context[:3])
            
            # Simple date extraction (you can enhance this with better parsing)
            if "Monday" in context_text or "Tuesday" in context_text or \
               "Wednesday" in context_text or "Thursday" in context_text or \
               "Friday" in context_text or "Saturday" in context_text or \
               "Sunday" in context_text or "ago" in context_text:
                historical_context = context_text[:200]  # Use first 200 chars
            else:
                # Fallback: mention it was previously recorded
                historical_context = "a previous session"
        
        # ====================================================================
        # PREPARE CONTEXT FOR LLM CHAIN
        # ====================================================================
        customer_profile = json.dumps(confirmed_facts, indent=2) if confirmed_facts else "{}"
        
        # ====================================================================
        # INVOKE MISMATCH VERIFICATION PROMPT WITH LLM
        # ====================================================================
        llm = create_llm(temperature=0.5)  # Balanced - professional but warm
        
        chain = MISMATCH_VERIFICATION_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "mismatch_details": mismatch_details,
                "historical_context": historical_context,
                "customer_profile": customer_profile,
            }
        )
        
        confirmation_message = response.content if hasattr(response, 'content') else str(response)
        
        state["clarification_question"] = confirmation_message
        state["clarification_needed"] = True
        state["agent_response"] = confirmation_message
        
        logger.info("❓ Polite mismatch confirmation request generated")
        logger.info(f"   Asking customer to confirm {len(mismatches)} field(s)")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Mismatch confirmation handler failed: {e}")
        state["agent_response"] = (
            "I noticed some differences in your information and I'd like to verify them with you. "
            "Could you please confirm the current details? "
        )
        return state


# ============================================================================
# HANDLER 3: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer questions using confirmed facts and context.
    
    Uses ChatOllama with structured prompts from prompts.py for consistency
    and maintainability.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        # Prepare context summaries
        facts_summary = json.dumps(facts, indent=2) if facts else "No confirmed facts"
        context_summary = "\n".join(context) if context else "No available context"
        
        # Create LLM chain
        llm = create_llm(temperature=0.3)  # Lower temp for factual responses
        
        # Use the query prompt from prompts.py
        chain = QUERY_ANSWER_CHAT_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
            }
        )
        
        answer = response.content if hasattr(response, 'content') else str(response)
        
        state["query_response"] = answer
        state["agent_response"] = answer
        logger.info("💬 Query answered")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Query handler failed: {e}")
        state["agent_response"] = "I apologize, I'm unable to answer that question at the moment. Please try again."
        return state


# ============================================================================
# HANDLER 4: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation with memory injection.
    
    Uses ChatOllama with structured prompts from prompts.py.
    Injects customer context to personalize responses.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        # Prepare context summaries
        facts_summary = json.dumps(facts, indent=2) if facts else "No customer profile yet"
        context_summary = "\n".join(context) if context else "No previous context"
        
        # Create LLM chain
        llm = create_llm(temperature=0.7)  # Slightly higher for conversational tone
        
        # Use the general response prompt from prompts.py
        chain = GENERAL_RESPONSE_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
            }
        )
        
        answer = response.content if hasattr(response, 'content') else str(response)
        
        state["agent_response"] = answer
        logger.info("💬 Response sent")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ General handler failed: {e}")
        state["agent_response"] = "I encountered an error while processing your request. Please try again."
        return state
