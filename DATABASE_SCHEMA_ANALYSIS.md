# LoanAgent Database Schema & Data Model Analysis

**Generated:** March 27, 2026

## CRITICAL ISSUES FOUND

### 1. ❌ SESSION_LOG TABLE NOT BEING POPULATED

**Severity:** HIGH

**Problem:**
- `session_log` table is created in schema but **never populated** during normal flow
- `end_session()` node in [core_nodes.py](backend/agent/core_nodes.py#L272) only stores response to ChromaDB, not to SQLite
- Session CRUD methods (`save_session()`, `add_turn_to_session()`) exist but are never called

**Evidence:**
- [end_session() in core_nodes.py](backend/agent/core_nodes.py#L272) does NOT call:
  - `db.save_session()` 
  - `db.add_turn_to_session()`
  - `db.end_session()`
- Methods exist in sqlite_store.py but are unused

**Impact:**
- No conversation turns are recorded
- Session summaries are never saved
- Cannot track session duration, agent_id, or turn count
- Field audit trail metadata (session_id) stored in field_change_log references non-existent sessions

**Fix Needed:**
- Update [end_session() around line 272](backend/agent/core_nodes.py#L272) to:
  1. Call `db.add_turn_to_session(session_id, "user", user_input)` after loading
  2. Call `db.add_turn_to_session(session_id, "assistant", agent_response)` before exit
  3. Call `db.end_session(session_id, summary=...)` to mark complete

---

### 2. ❌ FIELD_CHANGE_LOG TABLE NOT BEING POPULATED

**Severity:** HIGH

**Problem:**
- `field_change_log` table is created in schema but **never populated** anywhere in the codebase
- `log_field_change()` method exists but is never called in handlers.py or core_nodes.py
- Field change tracking is completely non-functional

**Evidence:**
- Method defined in [sqlite_store.py line 772](backend/memory/sqlite_store.py#L772)
- Called in test code ([sqlite_store.py line 1038-1045](backend/memory/sqlite_store.py#L1038)) but NOT in production code
- Zero references in [handlers.py](backend/agent/handlers.py) or [core_nodes.py](backend/agent/core_nodes.py)

**Impact:**
- No audit trail of field changes
- Cannot track conflicts, confirmations, or who confirmed what
- `get_unconfirmed_conflicts()` will always return empty
- `field_change_log` is dead code

**Fix Needed:**
- Call `db.log_field_change()` in [handle_memory_update() around line 140](backend/agent/handlers.py#L140) after updating each field:
  ```python
  for field_name, field_data in valid_schema_fields.items():
      old_value = existing_field.current.value if existing_field else None
      new_value = field_data["value"]
      db.log_field_change(
          customer_id=customer_id,
          field_name=field_name,
          session_id=session_id,
          old_value=str(old_value),
          new_value=str(new_value),
          conflict_detected=conflict_detected
      )
  ```

---

### 3. ❌ GET_CONFIRMED_FACTS() MISSING FIELDS

**Severity:** HIGH

**Problem:**
- `get_confirmed_facts()` returns incomplete customer profile
- Missing 13+ important fields that are stored in database

**Fields Stored but NOT Retrieved:**

**NonPII Missing (5 fields):**
1. `employment_history` - Full EmploymentHistory list
2. `cibil_last_checked` - Date CIBIL was last checked
3. `loan_request` - LoanRequest object (loan_type, loan_amount, tenure_months, purpose)
4. `documents_submitted` - DocumentSubmission list

**PII Missing (6 fields):**
1. `co_applicants` - List of CoApplicant objects
2. `guarantors` - List of Guarantor objects
3. `pan_hash` - PAN document hash (used for dedup)
4. `aadhaar_hash` - Aadhaar document hash (used for dedup)

**Data Type Mismatch:**
- `employment_history` stored as JSON array of models, but `get_confirmed_facts()` ignores it
- `documents_submitted` stored as JSON array, but not returned
- `co_applicants` and `guarantors` stored as JSON (encrypted), but not extracted

**Evidence:**
- [save_customer_memory() line 220-235](backend/memory/sqlite_store.py#L220) saves all these fields
- [get_confirmed_facts() line 510-595](backend/memory/sqlite_store.py#L510) only extracts 12 fields
- Complete gap in coverage for complex types

**Impact:**
- Agent can't access employment history when answering questions about jobs
- Loan request details unavailable to agent
- Co-applicants and guarantors unknown
- Document submission tracking impossible
- Handlers.py loads full memory but core_nodes.py can't use most of it

**Fix Needed:**
- Add extraction logic for all missing fields in `get_confirmed_facts()`:
  ```python
  # Add to nonpii_fields extraction
  employment_history_json = r.get("employment_history_json")
  if employment_history_json:
      employment_history = json.loads(employment_history_json)
      confirmed_facts["employment_history"] = employment_history
  
  # Add to pii_fields extraction
  co_applicants_encrypted = p.get("co_applicants_encrypted")
  if co_applicants_encrypted:
      decrypted = self.encryption.decrypt(co_applicants_encrypted)
      co_applicants = json.loads(decrypted)
      confirmed_facts["co_applicants"] = co_applicants
  ```

---

### 4. ❌ FIELD NAME MAPPING INCONSISTENCY IN HANDLERS.PII_FIELDS

**Severity:** MEDIUM

**Problem:**
- [handlers.py line 157-161](backend/agent/handlers.py#L157) defines PII field mapping but has inconsistencies with database schema

**Evidence:**
```python
pii_fields = {
    'full_name', 'date_of_birth', 'gender', 'marital_status',
    'primary_phone', 'current_address', 'city', 'state', 'pincode',
    'employer_name', 'years_at_current_job'
}
```

**Problem Details:**
1. Database columns are `full_name_encrypted` but mapping uses `full_name`
2. The code does `setattr(pii, field_name, entity)` which sets `pii.full_name` (without _encrypted suffix)
3. When loading, it correctly looks for `full_name_encrypted` column
4. Mismatch between what's set in model vs what's stored

**Impact:**
- While it works through model_dump_json(), it creates confusion
- Field mapping is not semantically correct

**Fix Needed:**
- Add missing identity-related PII fields:
  ```python
  pii_fields = {
      'full_name', 'date_of_birth', 'gender', 'marital_status',
      'primary_phone', 'current_address', 'city', 'state', 'pincode',
      'employer_name', 'years_at_current_job',
      'pan_hash', 'aadhaar_hash',  # Add these
      'co_applicants', 'guarantors'  # Add these
  }
  ```

---

### 5. ⚠️ LOAN_REQUEST MODEL FIELDS NOT IN CONFIRMED FACTS

**Severity:** MEDIUM

**Problem:**
- LoanRequest (with loan_type, loan_amount, tenure_months, purpose) stored but not retrievable
- When agent needs to answer "What loan amount did you request?" → **UNAVAILABLE**

**Evidence:**
- [models.py line 168-172](backend/memory/models.py#L168) defines LoanRequest structure
- [save_customer_memory() line 233](backend/memory/sqlite_store.py#L233) saves as JSON
- [get_confirmed_facts() line 510-595](backend/memory/sqlite_store.py#L510) **does not extract it**

**Impact:**
- Loan request context missing from agent responses
- Handlers load loan_request but retriever can't access it

**Fix Needed:**
```python
# In get_confirmed_facts(), add after NonPII fields extraction:
if r.get("loan_request_json"):
    confirmed_facts["loan_request"] = json.loads(r["loan_request_json"])
```

---

### 6. ⚠️ DOCUMENT SUBMISSION TRACKING INCOMPLETE

**Severity:** MEDIUM

**Problem:**
- DocumentSubmission list stored as JSON but not retrievable via `get_confirmed_facts()`
- Agent can't track which documents were submitted

**Evidence:**
- [save_customer_memory() line 234](backend/memory/sqlite_store.py#L234) stores as `documents_submitted_json`
- [get_confirmed_facts()](#section-3-get_confirmed_facts-missing-fields) doesn't extract it
- Only application_status extracted, not document details

**Impact:**
- "What documents have I submitted?" → Cannot answer
- No visibility into document status (pending_review, verified, rejected)

**Fix Needed:**
```python
# In get_confirmed_facts():
docs_json = r.get("documents_submitted_json")
if docs_json:
    docs = json.loads(docs_json)
    confirmed_facts["documents_submitted"] = docs
```

---

### 7. ⚠️ EMPLOYMENT HISTORY NOT ACCESSIBLE

**Severity:** MEDIUM

**Problem:**
- EmploymentHistory list stored in database but cannot be queried via `get_confirmed_facts()`
- Agent cannot answer questions about employment

**Evidence:**
- [save_customer_memory() line 224-227](backend/memory/sqlite_store.py#L224) saves employment_history_json
- [get_confirmed_facts()](#section-3-get_confirmed_facts-missing-fields) completely skips it
- No extraction to confirmed_facts

**Data Structure Mismatch:**
- Stored as array of EmploymentHistory objects with nested FixedEntity fields
- `get_confirmed_facts()` expects simple JSON extraction

**Impact:**
- "How long have you worked at your current job?" → No data access
- "What was your previous employment?" → Unavailable

**Fix Needed:**
```python
emp_history_json = r.get("employment_history_json")
if emp_history_json:
    confirmed_facts["employment_history"] = json.loads(emp_history_json)
```

---

### 8. ⚠️ CIBIL_LAST_CHECKED TIMESTAMP NOT IN CONFIRMED FACTS

**Severity:** LOW

**Problem:**
- `cibil_last_checked` is a timestamp column in database but not returned by `get_confirmed_facts()`

**Evidence:**
- [save_customer_memory() line 229](backend/memory/sqlite_store.py#L229) stores it
- [get_confirmed_facts()](#section-3-get_confirmed_facts-missing-fields) never retrieves it
- Stored as TEXT (ISO format), can be easily added

**Impact:**
- Agent can see CIBIL score but not when it was last checked
- Slightly degraded time-aware responses

**Fix Needed:**
```python
if r.get("cibil_last_checked"):
    confirmed_facts["cibil_last_checked"] = r["cibil_last_checked"]
```

---

### 9. ⚠️ PAN_HASH AND AADHAAR_HASH NOT ACCESSIBLE

**Severity:** LOW

**Problem:**
- Document hashes stored in PII table but not retrievable
- May be needed for deduplication or verification queries

**Evidence:**
- [save_customer_memory() line 361-362](backend/memory/sqlite_store.py#L361) saves pan_hash and aadhaar_hash
- [get_confirmed_facts()](#section-3-get_confirmed_facts-missing-fields) doesn't extract them

**Impact:**
- Hashes are one-way, not reversible, so they're not privacy-sensitive
- Could be useful for audit/verification but currently inaccessible

---

## SCHEMA CONSISTENCY MATRIX

| Field | Pydantic Model | SQLite NonPII | SQLite PII | Save ✓/✗ | Load ✓/✗ | Get Confirmed ✓/✗ |
|-------|---|---|---|---|---|---|
| **monthly_income** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **income_type** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **total_work_exp** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **employment_history** | ✓ (List) | ✓ | ✗ | ✓ | ✓ | ✗ |
| **cibil_score** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **cibil_last_checked** | ✓ (datetime) | ✓ | ✗ | ✓ | ✓ | ✗ |
| **total_existing_emi** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **number_of_active_loans** | ✓ (FixedEntity) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **loan_request** | ✓ (LoanRequest) | ✓ | ✗ | ✓ | ✓ | ✗ |
| **documents_submitted** | ✓ (List) | ✓ | ✗ | ✓ | ✓ | ✗ |
| **application_status** | ✓ (Enum) | ✓ | ✗ | ✓ | ✓ | ✓ |
| **full_name** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **date_of_birth** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **gender** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **marital_status** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **pan_hash** | ✓ (str) | ✗ | ✓ | ✓ | ✓ | ✗ |
| **aadhaar_hash** | ✓ (str) | ✗ | ✓ | ✓ | ✓ | ✗ |
| **primary_phone** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **current_address** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **city** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **state** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **pincode** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **employer_name** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **years_at_current_job** | ✓ (FixedEntity) | ✗ | ✓ | ✓ | ✓ | ✓ |
| **co_applicants** | ✓ (List) | ✗ | ✓ | ✓ | ✓ | ✗ |
| **guarantors** | ✓ (List) | ✗ | ✓ | ✓ | ✓ | ✗ |

---

## UNUSED DATABASE FEATURES

### 1. session_log Table (Complete Non-Use)
- **Status:** Created but never populated
- **Purpose:** Track conversation sessions
- **Current Usage:** 0% (test code only)
- **Methods Available:** `save_session()`, `load_session()`, `get_customer_sessions()`, `end_session()`, `add_turn_to_session()`
- **Fix:** Implement session tracking in [core_nodes.py](backend/agent/core_nodes.py)

### 2. field_change_log Table (Complete Non-Use)
- **Status:** Created but never populated  
- **Purpose:** Audit trail of all field changes
- **Current Usage:** 0% (test code only)
- **Methods Available:** `log_field_change()`, `confirm_field_change()`, `get_field_changes()`, `get_unconfirmed_conflicts()`
- **Fix:** Implement field change logging in [handlers.py](backend/agent/handlers.py)

### 3. CoApplicant Model
- **Status:** Defined in schema, stored in database, never retrieved
- **Storage:** Stored as JSON in `co_applicants_encrypted` column
- **Access:** Not in `get_confirmed_facts()`
- **Impact:** Agent doesn't know about co-applicants

### 4. Guarantor Model  
- **Status:** Defined in schema, stored in database, never retrieved
- **Storage:** Stored as JSON in `guarantors_encrypted` column
- **Access:** Not in `get_confirmed_facts()`
- **Impact:** Agent doesn't know about guarantors

### 5. EmploymentHistory List
- **Status:** Defined in schema, stored in database, never retrieved
- **Storage:** Stored as JSON array in `employment_history_json` column
- **Access:** Not in `get_confirmed_facts()`

### 6. DocumentSubmission List
- **Status:** Defined in schema, stored in database, never retrieved
- **Storage:** Stored as JSON array in `documents_submitted_json` column
- **Access:** Not in `get_confirmed_facts()`
- **Fields in Model:** doc_type, submitted_at, status, verification_notes, verified_by, verification_date
- **Query Methods:** None available yet

---

## DATA TYPE MISMATCHES

### 1. Employment History List Deserialization Issue
**File:** [sqlite_store.py line 397-403](backend/memory/sqlite_store.py#L397)

**Problem:** 
- Stored as JSON array of dicts with nested FixedEntity objects
- When loading, FixedEntity fields in employment records are deserialized properly
- But `get_confirmed_facts()` doesn't extract this complex type

**Current Code:**
```python
employment_history = [
    EmploymentHistory.model_validate(item) for item in raw_list
]
```

**Expected in get_confirmed_facts():** Should extract and validate similarly

### 2. Co-applicants List Encryption/Serialization
**File:** [sqlite_store.py line 236-237](backend/memory/sqlite_store.py#L236)

**Problem:**
- Stored as JSON string (not encrypted even though in PII table)
- Stored in `co_applicants_encrypted` column name but not actually encrypted
- [The encryption loop at line 261-265](backend/memory/sqlite_store.py#L261) skips list fields

**Evidence:**
```python
"co_applicants": json.dumps(
    [c.model_dump() for c in pii.co_applicants], default=str
),
"guarantors": json.dumps(
    [g.model_dump() for g in pii.guarantors], default=str
),
```

**Then at line 261:**
```python
for field in self.PII_ENCRYPTED_FIELDS:
    if field in pii_data and pii_data[field]:
        try:
            pii_data[field] = self.encryption.encrypt(pii_data[field])
```

**Issue:** `co_applicants` and `guarantors` are in PII_ENCRYPTED_FIELDS but their JSON is being encrypted as strings, not individual values

---

## RECOMMENDATION SUMMARY

### Critical (Must Fix Immediately)
1. **Implement session tracking** - Call session methods in end_session node
2. **Implement field change logging** - Call log_field_change in handle_memory_update
3. **Complete get_confirmed_facts()** - Extract all 13 missing fields

### High Priority (Should Fix Soon)
4. Add employment_history to confirmed facts
5. Add loan_request to confirmed facts
6. Add documents_submitted to confirmed facts
7. Add co_applicants and guarantors to confirmed facts

### Medium Priority (Nice to Have)
8. Add cibil_last_checked to confirmed facts
9. Add pan_hash and aadhaar_hash to confirmed facts (if needed for queries)
10. Clarify co_applicants/guarantors encryption strategy

---

## SCHEMA DESIGN HEALTHY AREAS

✅ **What's Working Well:**

1. **FixedEntity Version History** - Properly tracks current/history with status
2. **Encryption Strategy** - Separate PII table with encrypted columns
3. **Foreign Keys** - Proper referential integrity (session_log, field_change_log)
4. **Indexes** - Good coverage on session and field change queries
5. **Pydantic Models** - Well-structured with validation rules
6. **JSON Storage** - Efficient for complex nested types (LoanRequest, EmploymentHistory)
7. **Status Enums** - PENDING/CONFIRMED/SUPERSEDED/RETRACTED tracking

---

## FILES REQUIRING CHANGES

1. [backend/memory/sqlite_store.py](backend/memory/sqlite_store.py#L510) - Update `get_confirmed_facts()` method
2. [backend/agent/handlers.py](backend/agent/handlers.py#L140) - Add field change logging
3. [backend/agent/core_nodes.py](backend/agent/core_nodes.py#L272) - Implement session tracking
