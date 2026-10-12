# Structured Defect Register
### Department of Economic Development — Government of Umm Al Quwain (DED UAQ)
*Updated on: October 12, 2026 | Total Identified Defects: 7*

---

## 1. Defect Severity & Priority Distribution

| Severity | Priority | Description | Defect Count | Active Defect IDs |
| :--- | :---: | :--- | :---: | :--- |
| **Critical** | **P0** | Blocker preventing core operation, data loss, security bypass | **0** | None |
| **High** | **P1** | Serious crash in exception path or database persistence failure | **2** | `DEF-002`, `DEF-003` |
| **Medium** | **P2** | Route collision, schema boundary gap, AppLocker policy block, bilingual swap bug | **4** | `DEF-001`, `DEF-004`, `DEF-005`, `DEF-007` |
| **Low** | **P3** | Code hygiene, unused variables, React render purity linter warnings | **1** | `DEF-006` |

---

## 2. Detailed Defect Dossiers

### [DEF-001] Duplicate Operation ID & route shadowing on POST /TradeName/CheckTransliteration
- **Severity:** `Medium` | **Priority:** `P2` | **Status:** `Open`
- **Affected Module / File:** `API Routes (trade_name.py)`
- **Associated Requirement:** `F7, F17` | **Related Test Case:** `TC-CHKTRANS-003`
- **Environment:** FastAPI Backend 1.0.0, Python 3.11

#### Steps to Reproduce:
Inspect backend/api/routes/trade_name.py. Notice /CheckTransliteration is defined on line 420 and duplicated on line 772.

#### Expected Result:
Endpoint defined once, returning expected_en in UPPERCASE per F17 with phonetic fallback.

#### Actual Result:
FastAPI emits duplicate Operation ID warning. Line 772 is shadowed / dead code and lacks uppercase conversion.

#### Supporting Evidence & Logs:
```text
FastAPI UserWarning: Duplicate Operation ID check_transliteration_TradeName_CheckTransliteration_post
```

#### Root Cause Analysis:
Duplicate decorator @router.post('/CheckTransliteration') in trade_name.py lines 420 and 772.

#### Recommended Corrective Action:
Remove duplicate definition at line 772 and consolidate phonetic fallback and uppercase conversion into line 420.

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-002] UnboundLocalError 'primary_name' in register_trade_name exception handler
- **Severity:** `High` | **Priority:** `P1` | **Status:** `Open`
- **Affected Module / File:** `Registration (trade_name.py)`
- **Associated Requirement:** `F2, F15` | **Related Test Case:** `TC-REG-004`
- **Environment:** FastAPI Backend 1.0.0, Python 3.11

#### Steps to Reproduce:
Submit POST /TradeName/Register with new name while db.commit() raises an exception (e.g. concurrency collision).

#### Expected Result:
Exception caught, rollback executed, clean JSON error message returned with HTTP 200 or 409.

#### Actual Result:
Crash with HTTP 500 UnboundLocalError: local variable 'primary_name' referenced before assignment on line 1013.

#### Supporting Evidence & Logs:
```text
UnboundLocalError: cannot access local variable 'primary_name' where it is not associated with a value at line 1013.
```

#### Root Cause Analysis:
primary_name initialized inside 'if exact_matches:' on line 919. If exact_matches is empty and commit fails on line 978, primary_name is unassigned when line 1013 executes.

#### Recommended Corrective Action:
Initialize primary_name and primary_name_ar at top of register_trade_name handler (before database checks).

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-003] Reviewer Brief persistence failure due to missing transaction commit in brief_worker.py
- **Severity:** `High` | **Priority:** `P1` | **Status:** `Open`
- **Affected Module / File:** `Reviewer Copilot (brief_worker.py & trade_name.py)`
- **Associated Requirement:** `E5, F20` | **Related Test Case:** `TC-COP-001`
- **Environment:** FastAPI Backend, SQLAlchemy 2.0 Async

#### Steps to Reproduce:
POST /TradeName/ValidateWithSuggestion with RequestId, then GET /TradeName/ReviewerBrief/{requestId}.

#### Expected Result:
Reviewer brief generated and committed to ReviewerBrief table, retrieved with HTTP 200.

#### Actual Result:
GET /TradeName/ReviewerBrief/{requestId} returns HTTP 404 Not Found because brief_worker.py flushes without commit.

#### Supporting Evidence & Logs:
```text
HTTP 404: Reviewer brief for request ID 'QA-BRIEF-...' not found.
```

#### Root Cause Analysis:
generate_brief calls await self.session.flush() instead of commit(), and ValidateWithSuggestion does not commit transaction before session close.

#### Recommended Corrective Action:
Add await self.session.commit() inside generate_brief and record_decision in brief_worker.py.

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-004] Windows AppLocker policy blocks Cython .pyd files in SQLAlchemy and PyMuPDF
- **Severity:** `Medium` | **Priority:** `P2` | **Status:** `Open`
- **Affected Module / File:** `Core Engine / Dependencies`
- **Associated Requirement:** `N5, Env` | **Related Test Case:** `TC-ENV-001`
- **Environment:** Windows 11 / Windows Server with WDAC / AppLocker

#### Steps to Reproduce:
Run python imports in user directory without pure-python fallback.

#### Expected Result:
Compiled extensions load or fall back to pure-Python equivalents automatically.

#### Actual Result:
ImportError: DLL load failed: An Application Control policy has blocked this file.

#### Supporting Evidence & Logs:
```text
ImportError: DLL load failed while importing _cache_key_cy
```

#### Root Cause Analysis:
Unsigned or user-profile .pyd DLLs restricted by enterprise Windows Application Control policy.

#### Recommended Corrective Action:
Disable Cython compiled .pyd in SQLAlchemy site-packages to engage pure Python .py files or sign DLLs.

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-005] Field-level validation gap: ValidateRequest accepts empty strings for NameAr and NameEn
- **Severity:** `Medium` | **Priority:** `P2` | **Status:** `Open`
- **Affected Module / File:** `Validation Schemas (validation.py)`
- **Associated Requirement:** `F1` | **Related Test Case:** `TC-VAL-001`
- **Environment:** Pydantic v2, FastAPI Backend

#### Steps to Reproduce:
POST /TradeName/ValidateWithSuggestion with payload {'NameAr': '', 'NameEn': ''}.

#### Expected Result:
Rejected at schema level with HTTP 422 Unprocessable Entity ('String should have at least 1 character').

#### Actual Result:
HTTP 200 returned, pipeline proceeds to invoke LLM analyzer and triggers unnecessary token consumption.

#### Supporting Evidence & Logs:
```text
Status 200 with decision='NEEDS_REVIEW' after wasting LLM tokens on empty strings
```

#### Root Cause Analysis:
ValidateRequest fields NameAr and NameEn defined as str = Field(...) without min_length=1.

#### Recommended Corrective Action:
Add min_length=1 to NameAr and NameEn fields in ValidateRequest schema.

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-006] Frontend Oxlint warnings for React purity and useEffect setState calls
- **Severity:** `Low` | **Priority:** `P3` | **Status:** `Open`
- **Affected Module / File:** `Frontend Components`
- **Associated Requirement:** `UI-UX` | **Related Test Case:** `TC-UI-006`
- **Environment:** Node.js 18+, React 19, Oxlint

#### Steps to Reproduce:
Run 'npm run lint' in frontend directory.

#### Expected Result:
Zero linter warnings across React components.

#### Actual Result:
15 warnings: Math.random() in useState initial state (ValidationTab.jsx), synchronous setState in useEffect.

#### Supporting Evidence & Logs:
```text
react(purity): Cannot call impure function during render (ValidationTab.jsx:52)
```

#### Root Cause Analysis:
Math.random() evaluated directly in useState initializer rather than lazy initializer function or useEffect.

#### Recommended Corrective Action:
Use lazy initial state () => `UAQ-REQ-${...}` and ensure useEffect dependencies are sanitized.

- **Retest / Verification Protocol:** `Pending Fix`

---

### [DEF-007] NameComposer appends English legal form to Arabic name and fails to strip Arabic legal form token during amendment
- **Severity:** `Medium` | **Priority:** `P2` | **Status:** `Open`
- **Affected Module / File:** `NameComposer (pipeline/name_composer.py)`
- **Associated Requirement:** `F11` | **Related Test Case:** `TC-COMP-002`
- **Environment:** Python 3.11, Pipeline NameComposer

#### Steps to Reproduce:
Call compose(name_ar='شركة النور ذ.م.م', name_en='Al Noor Co LLC', operation_type='legal_form_amend', old_legal_form='LLC', new_legal_form='Sole Proprietorship').

#### Expected Result:
Old Arabic legal form 'ذ.م.م' stripped and Arabic new legal form applied; no English string appended to Arabic name.

#### Actual Result:
effective_ar becomes 'شركة النور ذ.م.م Sole Proprietorship' because string.replace() looked for English 'LLC' and appended English 'Sole Proprietorship' to Arabic text.

#### Supporting Evidence & Logs:
```text
effective_ar: 'شركة النور ذ.م.م Sole Proprietorship'
```

#### Root Cause Analysis:
Line 149 uses effective_ar.replace(old_legal_form) where old_legal_form is English token, and line 153 appends new_legal_form without Arabic translation mapping.

#### Recommended Corrective Action:
Use bilingual legal form dictionary mapping (e.g. {'LLC': 'ذ.م.م', 'Sole Proprietorship': 'مؤسسة فردية'}) to strip and append corresponding language tokens.

- **Retest / Verification Protocol:** `Pending Fix`

---
