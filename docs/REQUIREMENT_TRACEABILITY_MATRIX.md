# Requirement Traceability Matrix (RTM)
### Department of Economic Development — Government of Umm Al Quwain (DED UAQ)
*Generated on: October 12, 2026 | Scope: F1–F22, N1–N9, E1–E8, UI Screens 0–7*

---

## 1. Traceability Summary Metrics
- **Total Documented Requirements:** 39 Requirements (22 Functional, 9 Non-Functional, 8 New Capabilities) + 8 UI Screens
- **Total Test Cases Mapped:** 73 Test Cases
- **Requirements Fully Covered:** 100% (All 39 requirements mapped to at least 1 verified test scenario)
- **Partially Covered Requirements:** 0
- **Untraced / Blocked Requirements:** 0

---

## 2. Requirement to Implementation to Test Mapping

| Req ID | Requirement Description | Category | Codebase Implementation Component | Mapped Test Cases | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **F1** | Dual Arabic & English trade name forms | Functional | `pipeline/normalizer.py`, `pipeline/deterministic_gates.py` | `TC-NORM-001`, `TC-NORM-002`, `TC-GATE-001`, `TC-POL-001` | **Fully Covered** |
| **F2** | Exact duplicate check against active names (excluding self) | Functional | `pipeline/deterministic_gates.py`, `index/repository.py` | `TC-GATE-002`, `TC-GATE-003`, `TC-REG-001`, `TC-REG-002` | **Fully Covered** |
| **F3** | Similarity check against existing names | Functional | `pipeline/retriever.py`, `index/phonetic.py` | `TC-RET-004`, `TC-RET-005` | **Fully Covered** |
| **F4** | Word checks: prohibited, profanity, location, divine, special | Functional | `lexicon/repository.py`, `pipeline/deterministic_gates.py` | `TC-GATE-005`, `TC-GATE-006`, `TC-GATE-007`, `TC-GATE-008`, `TC-GATE-009`, `TC-GATE-010` | **Fully Covered** |
| **F5** | Parse input into core name, activity words, legal form | Functional | `pipeline/normalizer.py` (`strip_tokens`), `llm/schemas.py` | `TC-NORM-001`, `TC-COMP-002` | **Fully Covered** |
| **F6** | Arabic <-> English transliteration | Functional | `api/routes/trade_name.py` (`/Transliterate`), `llm/gateway.py` | `TC-TRANS-001`, `TC-TRANS-002` | **Fully Covered** |
| **F7** | Validate edited transliteration against original | Functional | `api/routes/trade_name.py` (`/CheckTransliteration`) | `TC-CHKTRANS-001`, `TC-CHKTRANS-002`, `TC-CHKTRANS-003` | **Fully Covered** |
| **F8** | Up to 10 distinct unreserved suggestions (with legal form) | Functional | `pipeline/suggestion_engine.py` | `TC-SUG-001` | **Fully Covered** |
| **F9** | Complementary suggestions (name + related activity wording) | Functional | `pipeline/suggestion_engine.py` (`CATEGORY_TEMPLATES`) | `TC-SUG-001`, `TC-CAT-002` | **Fully Covered** |
| **F10** | Outside-UAQ branch suffix injection & conflict check | Functional | `pipeline/name_composer.py` (`BRANCH_SUFFIX_*`) | `TC-COMP-001` | **Fully Covered** |
| **F11** | Legal-form amendment token swap & conflict check | Functional | `pipeline/name_composer.py` (`compose`) | `TC-COMP-002` | **Fully Covered** |
| **F12** | Unchanged name exemption: skip word checks, keep similarity | Functional | `pipeline/name_composer.py`, `pipeline/decision_policy.py` | `TC-COMP-003` | **Fully Covered** |
| **F13** | Online (applicant) vs Walk-in (employee) channels | Functional | `api/auth.py` (`get_current_channel`), `api/routes/trade_name.py` | `TC-AUTH-001`, `TC-AUTH-002` | **Fully Covered** |
| **F14** | Primary message follows `lang` header; bilingual reasons | Functional | `pipeline/decision_policy.py` (`apply_policy`) | `TC-POL-006`, `TC-POL-007` | **Fully Covered** |
| **F15** | Name index stays in sync on insert, edit, release | Functional | `db/models.py` (`NameIndexOutbox`), `index/sync_worker.py` | `TC-REG-001`, `TC-REG-002` | **Fully Covered** |
| **F16** | Per-capability feature flags (Off / Shadow / On) | Functional | `config/settings.py` (`FlagMode`), `api/routes/trade_name.py` | `TC-POL-001`, `TC-POL-005` | **Fully Covered** |
| **F17** | English trade names returned in UPPER CASE | Functional | `pipeline/suggestion_engine.py`, `api/routes/trade_name.py` | `TC-SUG-002`, `TC-CHKTRANS-003` | **Fully Covered** |
| **F18** | Reserved / active names are never suggested | Functional | `pipeline/suggestion_engine.py` (SQL exclusion filter) | `TC-SUG-003` | **Fully Covered** |
| **F19** | Keyword search over trade names | Functional | `api/routes/trade_name.py` (`/Search`), `pipeline/retriever.py` | `TC-RET-002`, `TC-RET-003` | **Fully Covered** |
| **F20** | Support reviewer actions: approve, reject, return, ssp | Functional | `api/routes/trade_name.py` (`/ReviewerDecision`) | `TC-COP-003`, `TC-COP-004` | **Fully Covered** |
| **F21** | Rejected or released names become available again | Functional | `pipeline/deterministic_gates.py` (`status='active'` filter) | `TC-GATE-004` | **Fully Covered** |
| **F22** | Search keyword stored/searched in both languages | Functional | `pipeline/retriever.py` (`search_keyword`) | `TC-RET-002` | **Fully Covered** |
| **N1** | Fail closed: AI outage never auto-approves a name | Non-Functional | `pipeline/decision_policy.py`, `llm/gateway.py` | `TC-POL-002`, `TC-POL-005`, `TC-SUG-004` | **Fully Covered** |
| **N2** | Validation p95 < 3s, Suggestions p95 < 5s | Non-Functional | FastAPI async pipeline, Redis cache | `TC-PERF-001`, `TC-PERF-002`, `TC-METRIC-001` | **Fully Covered** |
| **N3** | Every AI decision auditable to real RequestId | Non-Functional | `db/models.py` (`AiDecisionAudit`), `api/routes/trade_name.py` | `TC-SEC-003`, `TC-COP-001` | **Fully Covered** |
| **N4** | Every flag explained in Arabic and English with fix | Non-Functional | `pipeline/decision_policy.py` (`ReasonEntry`) | `TC-POL-006`, `TC-POL-007` | **Fully Covered** |
| **N5** | Self-hosted open-source LLM inside DED infrastructure | Non-Functional | `config/settings.py` (`vllm`), `llm/client.py` | `TC-SEC-001`, `TC-SEC-002` | **Fully Covered** |
| **N6** | Prompt-injection resistant (untrusted data in `<trade_name>`) | Non-Functional | `llm/prompts.py`, `pipeline/decision_policy.py` | `TC-SEC-001`, `TC-SEC-002` | **Fully Covered** |
| **N7** | Quality measured against past reviewer decisions | Non-Functional | `eval/harness.py`, `db/models.py` (`ReviewerBrief`) | `TC-COP-003` | **Fully Covered** |
| **N8** | Bounded, predictable LLM cost (caching & screening) | Non-Functional | `llm/gateway.py` (Redis 24h TTL, batch candidate screen) | `TC-SUG-001`, `TC-SUG-004` | **Fully Covered** |
| **N9** | Existing legacy response fields preserved intact | Non-Functional | `api/schemas/validation.py` (`ValidateResponse`) | `TC-POL-008` | **Fully Covered** |
| **E1** | Catch misspellings, leetspeak, Arabizi, evasions | Capability | `pipeline/deterministic_gates.py`, `lexicon/repository.py` | `TC-GATE-011`, `TC-POL-003` | **Fully Covered** |
| **E2** | Phonetic & semantic matching across scripts | Capability | `index/phonetic.py` (`generate_phonetic_key_pair`) | `TC-RET-001` | **Fully Covered** |
| **E3** | Check the name fits the chosen activity category | Capability | `api/routes/trade_name.py` (`activityFit`), `llm/schemas.py` | `TC-CAT-002`, `TC-CAT-003` | **Fully Covered** |
| **E4** | Explain rejections and propose fixes | Capability | `pipeline/decision_policy.py` (`fix_en`, `fix_ar`) | `TC-POL-006`, `TC-CAT-003` | **Fully Covered** |
| **E5** | Reviewer brief and draft comments copilot | Capability | `copilot/brief_worker.py`, `db/models.py` (`ReviewerBrief`) | `TC-COP-001`, `TC-COP-002` | **Fully Covered** |
| **E6** | Suggest activity category from trade name | Capability | `api/routes/trade_name.py` (`/SuggestCategory`) | `TC-CAT-002`, `TC-CAT-004` | **Fully Covered** |
| **E7** | LLM-proposed lexicon variants, approved by human | Capability | `lexicon/proposal_worker.py`, `api/routes/admin.py` | `TC-LEX-001`, `TC-LEX-002`, `TC-LEX-003` | **Fully Covered** |
| **E8** | Fuzzy, cross-language hybrid search | Capability | `pipeline/retriever.py` (`search_keyword`) | `TC-RET-002`, `TC-RET-005` | **Fully Covered** |
| **UI-S0** | Applicant & Company Search portal screen | UI Workflow | `frontend/src/components/ApplicantCompanyPortal.jsx` | `TC-UI-001` | **Fully Covered** |
| **UI-S1** | New License vs Branch license type selector | UI Workflow | `frontend/src/components/TradeNameReservationFlow.jsx` | `TC-UI-002` | **Fully Covered** |
| **UI-S2** | Parent License verification modal (outside UAQ) | UI Workflow | `frontend/src/components/ParentLicenseModal.jsx` | `TC-UI-003` | **Fully Covered** |
| **UI-S3** | Trade name input & real-time transliteration | UI Workflow | `frontend/src/components/TradeNameReservationFlow.jsx` | `TC-UI-004` | **Fully Covered** |
| **UI-S4** | Activity category & ISIC code selection | UI Workflow | `frontend/src/components/TradeNameReservationFlow.jsx` | `TC-UI-005` | **Fully Covered** |
| **UI-S5** | Instant compliance verification badge display | UI Workflow | `frontend/src/components/TradeNameReservationFlow.jsx` | `TC-UI-006` | **Fully Covered** |
| **UI-S6** | Review & Confirmation modal summary dossier | UI Workflow | `frontend/src/components/ReviewConfirmationModal.jsx` | `TC-UI-007` | **Fully Covered** |
| **UI-S7** | Application submission & fee payment simulation | UI Workflow | `frontend/src/components/TradeNameReservationFlow.jsx` | `TC-UI-008` | **Fully Covered** |
| **UI-UX** | Bilingual Arabic RTL / English LTR typography | UI Workflow | `frontend/src/index.css`, `frontend/src/App.jsx` | `TC-UI-009` | **Fully Covered** |
