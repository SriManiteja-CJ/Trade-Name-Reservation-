# Test Execution Report
### Department of Economic Development — Government of Umm Al Quwain (DED UAQ)
*Executed on: October 12, 2026 10:49:40 | Environment: Local Python 3.11 / SQLite In-Memory Isolation*

---

## 1. Consolidated Execution Summary

| Metric Category | Count / Percentage | Formula / Definition |
| :--- | :---: | :--- |
| **Total Test Cases** | **73** | Complete documented test inventory |
| **Executed Test Cases** | **73** | Tests triggered against active runtime |
| **Passed Test Cases** | **69** | Tests matching expected results |
| **Failed Test Cases** | **4** | Tests catching genuine defects or gaps |
| **Blocked Test Cases** | **0** | Tests blocked due to external factors |
| **Execution Coverage** | **100.00%** | `Executed / Total × 100` |
| **Pass Rate (Executed Tests)** | **94.52%** | `Passed / (Passed + Failed) × 100` |

### Positive vs Negative Scenario Analysis
- **Positive Scenarios:** 44 Total | 43 Passed | 1 Failed (Pass Rate: 97.7%)
- **Negative & Boundary Scenarios:** 29 Total | 26 Passed | 3 Failed (Pass Rate: 89.7%)

---

## 2. Detailed Test Execution Log

| Test ID | Module | Type | Status | Latency | Expected Result | Actual Result / Evidence | Defect ID |
| :--- | :--- | :---: | :---: | :---: | :--- | :--- | :---: |
| `TC-NORM-001` | `Normalization` | Positive | ✅ Pass | 0.05ms | Normalized to 'مخبز الامل للحلويات ذ.م.م' | Normalized: 'مخبز الامل للحلويات ذ.م.م' | - |
| `TC-NORM-002` | `Normalization` | Positive | ✅ Pass | 0.01ms | Normalized to 'creative technology l.l.c.' | Normalized: 'creative technology l.l.c.' | - |
| `TC-NORM-003` | `Normalization` | Boundary | ✅ Pass | 0.02ms | Gracefully handles mixed symbols and numbers | EN: 'cloud-9 & alpha_100!!!', AR: 'سحابه-9 والفا_100!!!' | - |
| `TC-COMP-001` | `NameComposer` | Positive | ✅ Pass | 1.6ms | Appends 'فرع أم القيوين' and 'Umm Al Quwain Branch' | Composed AR: 'الرواد للاستشارات فرع أم القيوين', EN: 'Al Rowad Consulting Umm Al Quwa | - |
| `TC-COMP-002` | `NameComposer` | Positive | ✅ Pass | 0.1ms | Old legal form stripped without corrupting core name | Swapped legal form tokens cleanly: 'Al Noor Co Sole Proprietorship' | - |
| `TC-COMP-003` | `NameComposer` | Positive | ✅ Pass | 0.24ms | skip_word_checks is set to True (word checks skipped) | skip_word_checks flag set to True | - |
| `TC-GATE-001` | `DeterministicGates` | Positive | ✅ Pass | 7451.87ms | Decision is OK or NEEDS_REVIEW, is_existing is False | HTTP 200, Decision: NEEDS_REVIEW, is_existing: False | - |
| `TC-GATE-002` | `DeterministicGates` | Negative | ✅ Pass | 3757.39ms | Decision is BLOCKED, is_existing is True | HTTP 200, decision: BLOCKED, is_existing: True | - |
| `TC-GATE-003` | `DeterministicGates` | Positive | ✅ Pass | 6.65ms | Exists is False (record excluded from check) | HTTP 200, Exists: False (self record excluded) | - |
| `TC-GATE-004` | `DeterministicGates` | Positive | ✅ Pass | 4.12ms | Exists is False (released name available for reuse) | HTTP 200, Exists: False (released name available for reuse) | - |
| `TC-GATE-005` | `DeterministicGates` | Negative | ✅ Pass | 4679.19ms | Decision is BLOCKED, Prohibted legacy flag is True | HTTP 200, decision: BLOCKED, Prohibted: True | - |
| `TC-GATE-006` | `DeterministicGates` | Negative | ✅ Pass | 5634.56ms | Decision is BLOCKED, Profanity legacy flag is True | HTTP 200, decision: BLOCKED, Profanity: True | - |
| `TC-GATE-007` | `DeterministicGates` | Negative | ✅ Pass | 3857.42ms | Decision is NEEDS_REVIEW, LocationNames flag is True | HTTP 200, decision: NEEDS_REVIEW, LocationNames: True | - |
| `TC-GATE-008` | `DeterministicGates` | Negative | ✅ Pass | 3232.35ms | Decision is NEEDS_REVIEW, AllahNames flag is True | HTTP 200, decision: NEEDS_REVIEW, AllahNames: True | - |
| `TC-GATE-009` | `DeterministicGates` | Negative | ✅ Pass | 2891.67ms | Decision is NEEDS_REVIEW, FamilyNames flag is True | HTTP 200, decision: NEEDS_REVIEW, FamilyNames: True | - |
| `TC-GATE-010` | `DeterministicGates` | Negative | ✅ Pass | 2703.62ms | Decision is BLOCKED, Special flag is True | HTTP 200, decision: BLOCKED, Special: True | - |
| `TC-GATE-011` | `DeterministicGates` | Negative | ✅ Pass | 2783.68ms | Decision is BLOCKED (variant detected) | HTTP 200, decision: BLOCKED (variant 'cazino' caught) | - |
| `TC-RET-001` | `HybridRetriever` | Positive | ✅ Pass | 0.1ms | Generates matching phonetic keys for cross-script comparison | Generated cross-script phonetic keys: 'ALNWR\|0LN0R', 'NWR\|N0R' | - |
| `TC-RET-002` | `HybridRetriever` | Positive | ✅ Pass | 1569.36ms | Returns matching trade names with similarity scores | HTTP 200, Total results: 2 | - |
| `TC-RET-003` | `HybridRetriever` | Boundary | ✅ Pass | 4.05ms | Returns HTTP 422 Unprocessable Entity for out-of-bound limits | HTTP 422 Unprocessable Entity for boundary violations (Limit 100 & Limit 0) | - |
| `TC-RET-004` | `HybridRetriever` | Positive | ✅ Pass | 2812.01ms | Similarity score is low (< 0.60 threshold) | HTTP 200, Similarity score: 0.4348 (well below 0.60 threshold) | - |
| `TC-RET-005` | `HybridRetriever` | Negative | ✅ Pass | 2946.47ms | Similarity score is elevated and similarNames populated | HTTP 200, Similarity: 0.8205, similarNames count: 6 | - |
| `TC-POL-001` | `DecisionPolicy` | Positive | ✅ Pass | 2927.55ms | Outcome is OK or NEEDS_REVIEW without hard blocks | HTTP 200, decision: NEEDS_REVIEW | - |
| `TC-POL-002` | `DecisionPolicy` | Security | ❌ Fail | 0.22ms | Outcome remains BLOCKED strictly (fail-closed invariant) | Exception: ValidationError: 1 validation error for LlmAnalyzerOutput
transliteration
 | - |
| `TC-POL-003` | `DecisionPolicy` | Negative | ❌ Fail | 0.18ms | Outcome is BLOCKED | Exception: ValidationError: 1 validation error for LlmAnalyzerOutput
transliteration
 | - |
| `TC-POL-004` | `DecisionPolicy` | Negative | ❌ Fail | 0.15ms | Outcome is NEEDS_REVIEW | Exception: ValidationError: 1 validation error for LlmAnalyzerOutput
transliteration
 | - |
| `TC-POL-005` | `DecisionPolicy` | Negative | ✅ Pass | 0.03ms | Hard gates execute; best outcome is NEEDS_REVIEW (never auto-appr | Policy evaluated deterministic rules cleanly: NEEDS_REVIEW | - |
| `TC-POL-006` | `DecisionPolicy` | Positive | ✅ Pass | 2762.75ms | Primary explanation rendered in Arabic | HTTP 200, Primary Arabic reason: الاسم يحتوي على اسم إلهي أو مقدس: "الرحمن". هذه ال.. | - |
| `TC-POL-007` | `DecisionPolicy` | Positive | ✅ Pass | 2739.28ms | Primary explanation rendered in English | HTTP 200, Primary English reason: The name contains a divine or sacred name: "الرحمن. | - |
| `TC-POL-008` | `DecisionPolicy` | Positive | ✅ Pass | 2806.59ms | All 8 legacy flags (Prohibted, Profanity, etc.) present with exac | HTTP 200, all 8 legacy boolean/float fields present with exact casing | - |
| `TC-SUG-001` | `SuggestionEngine` | Positive | ✅ Pass | 616.58ms | Generates 1 to 10 unique, unreserved suggestions | Generated 5 suggestions | - |
| `TC-SUG-002` | `SuggestionEngine` | Positive | ✅ Pass | 532.99ms | All suggested English trade names are returned in UPPERCASE | All 5 suggestions have uppercase English names | - |
| `TC-SUG-003` | `SuggestionEngine` | Negative | ✅ Pass | 726.61ms | Reserved and active registry names are never suggested | No reserved/active trade names in generated suggestion pool | - |
| `TC-SUG-004` | `SuggestionEngine` | Positive | ✅ Pass | 0.04ms | Deterministic templates cover categories 1, 3, 4 without AI | Deterministic template dictionary defined for categories 1, 3, 4 (4 categories) | - |
| `TC-TRANS-001` | `Transliteration` | Positive | ✅ Pass | 1278.75ms | Returns phonetically compliant Arabic trade name | HTTP 200, Arabic: 'مودرن تك للحلول', Confidence: 0.95 | - |
| `TC-TRANS-002` | `Transliteration` | Boundary | ✅ Pass | 2.56ms | Gracefully returns empty string without error | HTTP 200, Empty string returned for whitespace input | - |
| `TC-CHKTRANS-001` | `Transliteration` | Positive | ✅ Pass | 1398.6ms | Returns consistent=True with high confidence | HTTP 200, consistent: True, confidence: 1.0 | - |
| `TC-CHKTRANS-002` | `Transliteration` | Negative | ✅ Pass | 1152.3ms | Returns consistent=False with low confidence | HTTP 200, consistent: False, confidence: 0.22 | - |
| `TC-CHKTRANS-003` | `Transliteration` | Positive | ❌ Fail | 1553.47ms | Returns expected_en in UPPERCASE ('SKY') | expected_en was not uppercase: SAMAA | `DEF-001` |
| `TC-CAT-001` | `ActivityCatalogue` | Positive | ✅ Pass | 2.94ms | Returns exactly 10 official DED categories with ISIC codes | HTTP 200, exactly 10 official DED activity categories returned | - |
| `TC-CAT-002` | `SuggestCategory` | Positive | ✅ Pass | 1734.41ms | is_match is True, suggested category is Food & Beverage | HTTP 200, is_match: True, suggested_category_code: COMM_001 | - |
| `TC-CAT-003` | `SuggestCategory` | Negative | ✅ Pass | 1826.44ms | mismatch_detected is True with bilingual explanation | HTTP 200, mismatch_detected: True, Reason: The trade name implies food & beverage or  | - |
| `TC-CAT-004` | `SuggestCategory` | Boundary | ✅ Pass | 992.28ms | Clarification question or representative activities returned | HTTP 200, clarification formulated or representative activities recommended | - |
| `TC-COP-001` | `ReviewerCopilot` | Positive | ✅ Pass | 10.99ms | Brief returned with flags, top similar names, and recommendation | HTTP 200, brief retrieved with recommendation: approve | - |
| `TC-COP-002` | `ReviewerCopilot` | Negative | ✅ Pass | 4.45ms | Returns HTTP 404 Not Found | HTTP 404 Not Found | - |
| `TC-COP-003` | `ReviewerCopilot` | Positive | ✅ Pass | 13.26ms | Decision recorded successfully with updated=True | HTTP 200, updated: True, decision: approve | - |
| `TC-COP-004` | `ReviewerCopilot` | Negative | ✅ Pass | 2.9ms | Returns HTTP 400 Bad Request | HTTP 400 Bad Request, detail: Invalid decision 'INVALID_DECISION_XYZ'. Allowed: appro | - |
| `TC-LEX-001` | `LexiconManager` | Positive | ✅ Pass | 20.07ms | Returns list of pending proposals with total count | HTTP 200, pending proposals count: 1 | - |
| `TC-LEX-002` | `LexiconManager` | Positive | ✅ Pass | 18.75ms | Entry updated with approved_by=ReviewerName | HTTP 200, proposal 22 approved by Admin_Mariam | - |
| `TC-LEX-003` | `LexiconManager` | Positive | ✅ Pass | 13.49ms | Entry marked with approved_by=REJECTED | HTTP 200, proposal marked REJECTED | - |
| `TC-LEX-004` | `LexiconManager` | Negative | ✅ Pass | 4.8ms | Returns HTTP 404 Not Found | HTTP 404 Not Found | - |
| `TC-LEX-005` | `LexiconManager` | Negative | ✅ Pass | 2.61ms | Returns HTTP 422 Unprocessable Entity | HTTP 422 Unprocessable Entity | - |
| `TC-REG-001` | `Registration` | Positive | ✅ Pass | 20.33ms | Returns success=True, status=registered, unique trade_name_id | HTTP 200, registered with ID: 1009, ref: REG-2B6D63E7 | - |
| `TC-REG-002` | `Registration` | Negative | ✅ Pass | 1009.8ms | Returns success=False, status=rejected, suggestions populated | HTTP 200, rejected with duplicate warning, suggestions count: 6 | - |
| `TC-REG-003` | `Registration` | Boundary | ✅ Pass | 2.67ms | Returns HTTP 400 Bad Request | HTTP 400 Bad Request, detail: At least one of NameAr or NameEn must be provided for r | - |
| `TC-REG-004` | `Registration` | Negative | ✅ Pass | 1100.56ms | Exception handled gracefully without UnboundLocalError crash | Handled without crashing: HTTP 200 | - |
| `TC-SEC-001` | `Security` | Security | ✅ Pass | 3615.56ms | Decision is BLOCKED strictly (N6 security pass) | HTTP 200, decision: BLOCKED | - |
| `TC-SEC-002` | `Security` | Security | ✅ Pass | 2853.17ms | Decision format intact, model does not execute prompt commands | HTTP 200, structured response maintained: decision=NEEDS_REVIEW | - |
| `TC-SEC-003` | `Audit` | Positive | ✅ Pass | 2765.87ms | Audit record created linking RequestId permanently | HTTP 200, transaction executed with RequestId: AUDIT-REQ-159fd1 | - |
| `TC-AUTH-001` | `Authentication` | Positive | ✅ Pass | 2594.32ms | Request resolved under 'online' channel | HTTP 200, channel authenticated as 'online' applicant | - |
| `TC-AUTH-002` | `Authentication` | Positive | ✅ Pass | 2826.81ms | Request resolved under 'walkin' channel | HTTP 200, channel resolved as 'walkin' employee | - |
| `TC-PERF-001` | `Performance` | Positive | ✅ Pass | 2833.52ms | Latency is strictly below 3.0 seconds | HTTP 200, response time: 2.834s (< 3.0s SLA) | - |
| `TC-PERF-002` | `Performance` | Positive | ✅ Pass | 629.73ms | Latency is strictly below 5.0 seconds | Suggestions generated in 0.630s (< 5.0s SLA) | - |
| `TC-METRIC-001` | `Observability` | Positive | ✅ Pass | 8.78ms | Exports Prometheus 0.0.4 metrics (validation_latency_seconds, out | HTTP 200, Prometheus metrics scraped successfully | - |
| `TC-UI-001` | `FrontendScreens` | Positive | ✅ Pass | 2.29ms | Portal screen connects to healthy API Gateway | API Gateway connected: Status Healthy, feature flags active | - |
| `TC-UI-002` | `FrontendScreens` | Positive | ✅ Pass | 0.0ms | TradeNameReservationFlow renders dual license radio cards | Screen 1 Radio selector supports 'new' (Inside UAQ) and 'branch' (Outside UAQ) | - |
| `TC-UI-003` | `FrontendScreens` | Positive | ✅ Pass | 0.0ms | Modal validates parent Emirate, License No, and Expiry Date | Screen 2 Parent License Modal opens when branch option selected | - |
| `TC-UI-004` | `FrontendScreens` | Positive | ✅ Pass | 622.88ms | Transliterates English name into Arabic seamlessly | Debounced transliteration generated: 'جلوبال للتقنية فينتوريس' | - |
| `TC-UI-005` | `FrontendScreens` | Positive | ✅ Pass | 1.73ms | Renders 10 official DED activity categories with search | Dropdown populated with 10 business categories | - |
| `TC-UI-006` | `FrontendScreens` | Positive | ✅ Pass | 3050.74ms | Displays OK/NEEDS_REVIEW/BLOCKED with legacy & additive badges | Instant validation displayed decision: NEEDS_REVIEW | - |
| `TC-UI-007` | `FrontendScreens` | Positive | ✅ Pass | 0.01ms | Presents comprehensive application summary and compliance declara | Review & Confirmation dossier compiles bilingual names, activities, and fee breakdown | - |
| `TC-UI-008` | `FrontendScreens` | Positive | ✅ Pass | 10.44ms | Generates unique registration reference and success certificate s | Application submitted, Reference: REG-772E3425, Status: registered | - |
| `TC-UI-009` | `FrontendScreens` | Positive | ✅ Pass | 0.26ms | Supports RTL Arabic (Cairo) and LTR English (Outfit) with luxury  | Frontend built successfully with RTL/LTR Cairo & Outfit styling (904 bytes) | - |