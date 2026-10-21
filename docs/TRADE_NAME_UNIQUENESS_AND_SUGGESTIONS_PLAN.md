# Dynamic Base-Name Extraction, Activity-Based Uniqueness, and Dynamic Suggestion Engine Implementation Plan

## 1. Architectural Philosophy: 100% Dynamic & Configurable
No trade names, brand variations, activity mappings, or descriptors will be hardcoded in the codebase. All logic will be fully dynamic, data-driven, and configurable.

```mermaid
flowchart TD
    A["Raw Input Trade Name\n(e.g., 'Cloudjune Technologies' / 'الساحة كافيه ومطعم')"] --> B["Stage 1: Dynamic Text Decomposition\n- Legal Form Stripping\n- Stopword & Grammatical Particles\n- Activity Descriptors (from Activity Catalogue)"]
    B --> C{"Confidence Check:\nIs Distinctive Base Name Found?"}
    C -->|No: Only Generic Descriptors| D["Fallback: Flag as Ambiguous / Generic\nTrigger NEEDS_REVIEW (Cannot silently approve)"]
    C -->|Yes: Base Name Isolated| E["Dynamic Base Name: 'Cloudjune'\nPreserved Descriptor: 'Technologies'"]
    
    E --> F["Stage 2: Activity-Scoped Database Verification (category_id)"]
    F -->|1. Exact / Canonical Match| G["Conflict: EXACT DUPLICATE (Blocked)"]
    F -->|2. Base Name in Active Records in category_id| H["Conflict: RESERVED BASE NAME (Blocked)\n'X is already registered under [Activity]...'"]
    F -->|3. High Confusing Similarity (>=85%)| I["Conflict: CONFUSINGLY SIMILAR (Needs Review)"]
    F -->|4. Clean in category_id| J["Status: AVAILABLE ✓\n(Allowed even if base name is active in other activities)"]
    
    H --> K["Stage 3: Dynamic Similar-Name Generator\n- Algorithmic Phonetic & Syllable Mutations\n- Compound Root Variations\n- LLM Dynamic Generation (when enabled)"]
    K --> L["Recombine with User's Descriptor: '{MutatedBase} {PreservedDescriptor}'\n+ Dynamic Arabic Transliteration"]
    L --> M["Stage 4: 100% Database Pre-Validation (Scoped to category_id)\n- Filter out reserved base names\n- Filter out existing full names\n- Filter out rapidfuzz >= 80% & lexicon blocks"]
    M --> N["Deliver Verified Available Suggestions in Explore Names"]
```

---

## 2. Hardcoded Assumptions Identified & How They Will Be Replaced

| Component | Current Hardcoded Assumption | Replaced With Dynamic Solution |
| :--- | :--- | :--- |
| **Descriptors** | Static Python set of ~30 hardcoded words in `suggestion_engine.py` | **Dynamic Descriptor Registry**: Extracted dynamically from `OFFICIAL_ACTIVITY_CATALOGUE` (all ISIC codes, representative activity keywords, and category names in EN & AR) + configurable corporate structure terms. |
| **Activity Mapping** | `CATEGORY_NAME_MAP = {"1": "...", "2": "..."}` | **Dynamic Catalogue Lookup**: Resolved directly from `OFFICIAL_ACTIVITY_CATALOGUE` by `category_id` or `code`. |
| **Brand Collision Handling** | Completely dropped any suggestion containing the brand or fell back to static list (`AURA TECH`, `AL SAHA CAFE`) | **Dynamic Phonetic & Morphological Mutation Engine**: Dynamically mutates *any* base name (syllables, rhymes, consonant skeletons, compound roots) and preserves the user's specific descriptor. |
| **Transliteration** | Hardcoded dictionaries (`"teja": "تيجا"`, `"noor": "نور"`, etc.) | **Dynamic Phonological Transliteration Engine**: Algorithmic rules for Arabization / Romanization capable of transliterating any novel proper noun. |
| **Cross-Activity Scope** | Fallback in `deterministic_gates.py` checked all categories if not found in current category | **Strict Activity Scoping**: Checks are strictly bounded to `category_id`. Cross-activity existence is permitted unless conflicting in that specific activity. |

---

## 3. Detailed Component Implementation Plan

### Component 1: Dynamic Base-Name Identification
**Location:** [backend/pipeline/base_name_extractor.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/base_name_extractor.py) (New modular component)
- **Token Analysis & Decomposition:**
  1. **Legal Entity Tokens:** Strips standard legal form identifiers (LLC, PJSC, FZE, Establishment, ذ.م.م, ش.م.ع, مؤسسة فردية) regardless of position (prefix, suffix, or infix).
  2. **Grammatical Connectors & Stopwords:** Removes relational particles (`and`, `&`, `for`, `of`, `the`, `و`, `لـ`, `في`, `من`).
  3. **Industry & Activity Descriptors:** Dynamic matching against activity terms loaded from `OFFICIAL_ACTIVITY_CATALOGUE` and corporate generic words.
  4. **Word Order Invariance:**
     - `Cloudjune Technologies` &rarr; Base Name: `Cloudjune`, Descriptor: `Technologies`
     - `Technologies Cloudjune` &rarr; Base Name: `Cloudjune`, Descriptor: `Technologies`
     - `Advanced Technology Cloudjune LLC` &rarr; Base Name: `Cloudjune`, Descriptor: `Advanced Technology`
     - `كلاودجون لتقنية المعلومات ذ.م.م` &rarr; Base Name: `كلاودجون`, Descriptor: `لتقنية المعلومات`
     - `مطعم وكافيه الساحة` &rarr; Base Name: `الساحة`, Descriptor: `مطعم وكافيه`
- **Ambiguity & Generic Protection:**
  - If a trade name consists solely of generic descriptors (e.g., `General Trading LLC` / `شركة التجارة العامة ذ.م.م`), the extractor flags `confidence = "low"`, `is_generic = True`.
  - The deterministic gates will **not** silently approve generic names; they will emit `NEEDS_REVIEW` requiring a distinctive brand element.

---

### Component 2: Activity-Specific Base-Name Reservation in Database
**Locations:**
- [backend/index/repository.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/index/repository.py)
- [backend/pipeline/deterministic_gates.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/deterministic_gates.py)

1. **`lookup_base_name_in_category` Repository Query:**
   - Queries `trade_name_index` for `status = 'active'` and `category_id = :target_category_id`.
   - Compares the candidate's extracted base name against existing records in that activity:
     - Exact base-name equality
     - Whole-word regex match `\b{base_name}\b`
   - If a match is found:
     - Emits `BLOCKED` with `source="reserved_base_name"`.
     - Message: `"Trade name '{input_name}' conflicts with protected base name '{base_name}', which is already reserved under {activity_name} by existing registration '{matched_name}'."`
2. **Cross-Activity Independence:**
   - The query strictly includes `AND category_id = :category_id`.
   - If the same base name is registered in Category 3 (Technology), but the user selects Category 1 (Commercial/Trading), the check in Category 1 passes.

---

### Component 3: Dynamic Similar-Name Suggestion Engine
**Location:** [backend/pipeline/suggestion_engine.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/suggestion_engine.py)

1. **Algorithmic Phonetic & Morphological Mutations (Zero Hardcoded Names):**
   - Given any base name `B` (e.g. `Cloudjune`, `Zentron`, `Falcone`, `Nibras`, `Al-Bahar`):
     - **Compound Split & Vary:** If `B` has recognizable compound components (e.g. `Cloud` + `june`), preserve the root and vary the secondary element with phonetically pleasing morphemes (`nine`, `jini`, `zone`, `nova`, `peak`, `sphere`, `spark`, `nest`, `wave`, `flux`, `craft`).
     - **Syllabic Rhyme & End Substitution:** Replace terminal syllables while maintaining vowel cadence (e.g. `-nova`, `-nine`, `-zone`, `-vance`, `-tron`, `-ix`, `-is`, `-on`, `-a`).
     - **Consonant Skeleton & Soundex Neighbors:** Generate sound-alike phonetic variations.
     - **Prefix Augmentation:** Attach modern prefixes (`Neo-`, `Omni-`, `Aura-`, `Nova-`) to the core stem.
2. **Descriptor Preservation:**
   - Recombines the generated base name with the user's preserved descriptor:
     - Input: `Cloudjune Technologies` &rarr; Suggestions: `Cloudnine Technologies`, `Cloudjini Technologies`, `Cloudzone Technologies`, `Cloudnova Technologies`.
     - Input: `Falcon Logistics` &rarr; Suggestions: `Falcova Logistics`, `Falzone Logistics`, `Falcop Logistics`.
3. **Dynamic Transliteration:**
   - Algorithmic EN &harr; AR transliteration converts names phonetically without hardcoded lookup tables.
4. **LLM Dynamic Generation (when enabled):**
   - When LLM mode is active, prompt the model with the applicant's base name, descriptor, and selected activity to generate 20 novel, structurally close base names (strictly forbidding the conflicting base name).
5. **Mandatory 100% Database Pre-Validation:**
   - Every candidate is checked against the database within `category_id`:
     - Must not equal any registered full name.
     - Must not contain any reserved base name in that activity.
     - Must not exceed confusing similarity threshold (`rapidfuzz < 80`).
     - Must pass lexicon checks.
   - **Guarantee:** No name is presented as available without passing active database verification.

---

### Component 4: Endpoint & Concurrency Safety
**Locations:**
- [backend/api/routes/trade_name.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/api/routes/trade_name.py)
- [backend/api/schemas/validation.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/api/schemas/validation.py)

1. **Consistent Rules Across All Endpoints:**
   - `POST /TradeName/ValidateWithSuggestion`
   - `GET /TradeName/IsTradeNameExist`
   - `POST /TradeName/Register`
2. **Transactional Safety:**
   - In `POST /TradeName/Register`, perform the base-name and exact duplicate check inside the database transaction immediately prior to `db.add()` and `db.commit()`.
   - Protects against simultaneous requests registering the same base name.

---

### Component 5: Frontend Experience
**Location:** [frontend/src/components/TradeNameReservationFlow.jsx](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/frontend/src/components/TradeNameReservationFlow.jsx)
1. **Dynamic Notification Display:**
   - `"${tradeName} is already registered under ${activityName}. Explore the following alternative trade names that may be available for registration."`
2. **Instant Reactivity on Activity Switch:**
   - Changing activity immediately re-evaluates availability against the new `category_id`.
3. **Card Adoption & Pre-Submission Revalidation:**
   - Clicking a card instantly populates input fields, confirms availability, and enables registration.

---

## 4. Verification & Acceptance Testing Plan

| Test Case | Trade Name Input | Selected Activity | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-1** | `Cloudjune Technologies` (Registered) | Technology Services (Cat 3) | **BLOCKED** (`exact_duplicate`). Notification displayed. Suggestions generated. |
| **TC-2** | `Cloudjune IT Solutions` | Technology Services (Cat 3) | **BLOCKED** (`reserved_base_name`). `Cloudjune` is reserved in Cat 3. |
| **TC-3** | `Cloudjune Digital Services` | Technology Services (Cat 3) | **BLOCKED** (`reserved_base_name`). |
| **TC-4** | `Cloudjune Cafe` | Cafe and Restaurant (Cat 1) | **AVAILABLE ✓** (Cross-activity independence). |
| **TC-5** | `Cloudjune Fashions` | Clothing and Retail (Cat 1) | **AVAILABLE ✓** (Cross-activity independence). |
| **TC-6** | Suggestions for TC-1 / TC-2 | Technology Services (Cat 3) | Suggestions: `Cloudnine Technologies`, `Cloudjini Technologies`, etc. **Zero** suggestions contain `Cloudjune`. |
| **TC-7** | Dynamic Unrelated Brand: `Apex Logistics` (Registered) | Logistics (Cat 8) | `Apex Express Delivery` is **BLOCKED** under Cat 8; `Apex Cafe` is **AVAILABLE** under Cat 1. |
| **TC-8** | Word Order Invariance | Cat 3 | `Technologies Cloudjune` extracts `Cloudjune` and blocks accordingly. |
| **TC-9** | Generic Input (e.g. `General Trading LLC`) | Cat 1 | Flagged as generic/ambiguous (`NEEDS_REVIEW`), not silently approved. |
| **TC-10** | Concurrent Registration | Cat 3 | Transaction-safe atomic verification blocks simultaneous race condition. |

---

## 5. Implementation Steps
1. [ ] Implement [backend/pipeline/base_name_extractor.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/base_name_extractor.py) with dynamic token decomposition and word-order invariance.
2. [ ] Update [backend/index/repository.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/index/repository.py) with dynamic `lookup_base_name_in_category`.
3. [ ] Update [backend/pipeline/deterministic_gates.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/deterministic_gates.py) to incorporate base-name reservation and remove global fallback.
4. [ ] Refactor [backend/pipeline/suggestion_engine.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/pipeline/suggestion_engine.py) to remove all hardcoded template lists and introduce the algorithmic mutation engine.
5. [ ] Update [backend/api/routes/trade_name.py](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/backend/api/routes/trade_name.py) for consistent dynamic validation and notification payload.
6. [ ] Update [frontend/src/components/TradeNameReservationFlow.jsx](file:///c:/Users/DELL/Desktop/Trade%20Name%20Intelligence%20Service/frontend/src/components/TradeNameReservationFlow.jsx) for reactive activity switching and notifications.
7. [ ] Run full automated test suite and browser validation across all test scenarios.
