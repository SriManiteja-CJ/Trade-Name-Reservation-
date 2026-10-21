# Trade Name Intelligence Service — Client Demo Script

## Demo purpose

Present the Trade Name Intelligence Service (TNIS) as a bilingual decision-support application for trade-name reservation and review in Umm Al Quwain. The demo should show how an applicant or officer can:

- Enter and assess a proposed Arabic and/or English trade name.
- Check the name against the selected business activity and available registry data.
- See compliance findings, similar-name risks, and alternative suggestions.
- Support human review with an officer-facing brief and recorded decision.
- Search the registry and administer controlled compliance terms.

TNIS supports decision-making; it is not a substitute for the competent authority's final legal or administrative decision.

## Before the meeting

### Environment checklist

- Start the backend and frontend and confirm both are responsive.
- Confirm the backend database is the intended demo database and contains only approved demo/test records.
- Confirm the activity catalogue loads and the activity categories used in the script are valid.
- Confirm any required LLM, Redis, and embedding services are reachable and their feature flags are in the intended mode.
- Prepare one known available test name and one or more known conflict names in the demo database. Confirm their Arabic/English forms, activity category, and status in advance.
- Prepare a request ID with a generated reviewer brief if demonstrating Reviewer Copilot.
- Use a staging/demo environment. Do not enter real applicant personal information or submit a real application during this walkthrough.
- Keep a browser tab open at the API health/docs endpoint for troubleshooting, not as a replacement for the live UI.

### Important presenter cautions

- The Applicant & Search landing screen contains static sample profile details and dashboard counts. Introduce these as prototype/demo data, not live applicant records or official service statistics.
- Registry Search has a client-side sample-data fallback when its backend request fails. Before presenting search results as registry results, confirm the backend request succeeded. If the service is unavailable, stop and disclose that the displayed sample results are illustrative.
- The reservation flow contains an offline fallback that can display a simulated registration/payment confirmation if its registration request fails. Do not present that fallback as a completed database registration or payment. Verify a successful backend response and resulting database record before describing registration as complete.
- The parent-licence upload/branch experience includes pre-populated demonstration details. Do not claim that document OCR or licence verification took place unless it has been separately verified in the environment.
- AI outcomes depend on configured services and feature-flag modes. In shadow mode, the AI may run for logging while not influencing the final decision. Avoid promising a particular AI output.
- Availability depends on registry contents, selected activity, deterministic rules, and configuration. A clean result means no configured conflict was found in this check; it is not a legal guarantee of approval.
- Any names below are examples only. Use known fixtures from the demo database for predictable results.

## Suggested run of show (15–20 minutes)

| Segment | Approx. time | Screen |
|---|---:|---|
| Welcome, purpose, and boundaries | 1 min | Applicant & Search |
| Applicant experience and bilingual controls | 2 min | Applicant & Search / Trade Name |
| New-name assessment and positive case | 4 min | Trade Name |
| Negative cases and recommendations | 4 min | Trade Name / Compliance |
| Registry search | 2 min | Registry Search |
| Officer review and governance | 3 min | Reviewer Copilot / Administration |
| Summary and questions | 1–3 min | Any |

## Presenter script

### 1. Welcome and objective

**Say**

“Thank you for joining. Today I’ll demonstrate the Trade Name Intelligence Service, or TNIS. Its goal is to help applicants and reviewers assess proposed trade names more consistently by bringing together bilingual name handling, activity-aware availability checks, compliance screening, similarity signals, and review support in one workflow.

“We’ll look at both positive and negative outcomes. A positive result means the configured checks did not find a blocking issue in this demo environment; it is not a promise of final approval. The competent officer retains the final decision.”

**Do**

1. Show the application shell and navigation.
2. Point out the English/Arabic language control.
3. Set expectations that the records and applicant dashboard are demonstration data unless connected to a verified live environment.

### 2. Applicant portal and navigation

**Say**

“The portal is the starting point for the applicant-facing journey. From here, a user can navigate to the trade-name reservation experience. The interface supports English and Arabic, including right-to-left layout for Arabic.”

**Do**

1. Open **Applicant & Search**.
2. If useful, open the service catalogue and show its search/filter interaction.
3. Avoid describing the displayed profile, license counts, request totals, or compliance percentage as live data; they are static presentation values in this screen.
4. Navigate to **Trade Name**.

### 3. New trade-name assessment — positive case

**Say**

“For a new name, the applicant provides the proposed name in Arabic and English and selects or describes the business activity. The two forms can be edited, and the interface provides transliteration assistance. The user can review the generated text rather than treating it as authoritative.”

**Do**

1. Select the new-licence flow.
2. Enter a prepared, distinctive demo name in both languages.
3. Select the known matching activity category. If the screen exposes a free-text activity description, enter the prepared activity too.
4. Show the Arabic/English transliteration assistance. Explain that transliteration supports data entry; it is not a legal translation certification.
5. Run **Analyze with AI**.
6. Wait for the response and inspect the activity recommendation, validation outcome, reasons, and any candidate suggestions.

**Say**

“The service composes and normalizes the supplied names, checks deterministic rules and registry conflicts, retrieves similar names, and may call configured AI services. The response is presented as an outcome with reasons rather than only a green or red indicator.

“For this prepared positive example, the configured checks did not find a blocking conflict. The result remains subject to the selected activity, current registry data, and officer review.”

**Positive-case interpretation**

- **OK / no blocking reason:** No configured blocking or review signal was returned for this request. It is not a final license or legal approval.
- **Suggestions shown:** These are candidates returned by the service for consideration. Confirm their response status and availability in the demo database before saying they are available.
- **Arabic/English pair:** Verify that the two names represent the intended brand and are acceptable to the applicant.

### 4. Negative case — exact or reserved-name conflict

**Say**

“Next I’ll use a prepared name that is already present in the demo registry for this activity. The system checks exact matches and, where configured, distinctive base-name reuse within the selected activity.”

**Do**

1. Enter the known conflict fixture in Arabic and English.
2. Select the category under which the record is registered.
3. Run the assessment.
4. Point out the blocked/review outcome, matched record details if returned, conflict type, and bilingual explanation.
5. If alternatives are returned, explain that they are suggestions to assess—not automatic reservations.

**Say**

“This is a negative availability case. The result identifies the conflict and gives the user a reason to choose a different name or send the case for review. Activity scoping matters: the result can differ if the activity is changed.”

### 5. Negative case — restricted or compliance term

**Say**

“The compliance checks can identify configured restricted terms and return a severity and explanation. For this example, I’ll use a safe, preapproved test fixture from the demo dataset; I won’t introduce offensive or sensitive material into the client session.”

**Do**

1. Use the prepared restricted-term fixture and run the validation.
2. Show the compliance reason and any bilingual remediation guidance.
3. Point out the legacy compliance flags if they are included in the response.

**Say**

“A configured hard-block term can prevent a clean pass; a review-level term can route the case for human assessment. The precise outcome depends on the term's configured category and severity.”

### 6. Negative case — generic, uncertain, or similar name

**Say**

“Not every name produces a definitive available/unavailable answer. Generic names may not provide a distinctive base name for a reliable uniqueness check, and near matches can require human review.”

**Do**

1. Enter a prepared generic test name, such as a combination made only from common business descriptors, and run the check.
2. Show the `NEEDS_REVIEW` outcome and the reason, if returned.
3. Optionally enter a prepared near-match fixture and show its similarity result.

**Say**

“This is an intentional uncertainty path: the application avoids representing an ambiguous result as a guaranteed approval. Similarity is a screening signal; an officer interprets the result in context.”

### 7. Negative case — activity mismatch or insufficient activity information

**Say**

“The activity recommendation helps check whether the stated business activity makes sense alongside the trade name. A mismatch or broad description can result in a suggested category or a clarification request.”

**Do**

1. Use a prepared mismatch example from the demo dataset—for example, a food-related name paired with a technology activity—only if the configured model/rules support that example.
2. Show the suggested activity, mismatch explanation, or clarification prompt if present.
3. If no activity was selected, show the category-required validation path in **Compliance** or the fast-check form instead of implying that a name can be approved without a category.

**Say**

“The recommendation helps guide the next step. It does not silently change the user's intended activity; the applicant or reviewer must confirm the correct category.”

### 8. Branch and legal-form scenarios

**Say**

“The interface also exposes branch and legal-form amendment scenarios. These demonstrate how operation type and legal form can affect name composition and validation.”

**Do**

1. If stable and verified in the demo environment, select the branch scenario and show the fields.
2. Show the legal-form amendment scenario in **Compliance** using its prepared preset if available.
3. Describe the fields as a workflow demonstration; do not claim an uploaded document was actually parsed or verified unless that integration has been independently confirmed.

**Say**

“The decision depends on the data supplied and the backend's configured rules. For operational use, the integration must pass verified licence and application data rather than relying on prefilled demonstration content.”

### 9. Compliance inspection

**Say**

“The Compliance screen lets us run the checks directly with an application/request ID, Arabic and English names, operation type, legal form, and activity category. It also includes quick transliteration and category-suggestion actions.”

**Do**

1. Open **Compliance**.
2. Show the available presets, but explain that preset outcomes depend on the current database and configuration.
3. Select a prepared positive preset or fill the prepared known-good fixture.
4. Show the response outcome, reasons, similarity details, and activity-fit information if returned.
5. Optionally show a prepared negative preset only if its expected response has been verified against this demo database.

**Say**

“The validation response preserves compatibility fields while adding structured reasons, decisions, similarity information, and suggestions. The same request ID can be used to retrieve a reviewer brief if brief generation is enabled.”

### 10. Registry Search and duplicate check

**Say**

“Registry Search provides keyword search and a fast existence check. Search results can help an officer or applicant understand what names are nearby in the active registry.”

**Do**

1. Open **Registry Search**.
2. Search a term known to exist in the demo registry.
3. Point out Arabic/English names, registry IDs, and similarity scores.
4. Use the duplicate-check form with the prepared fixture, including its activity category where requested.

**Say**

“The score is a similarity signal, not itself a legal ruling. We should base decisions on the full record and the relevant rules.”

**If live search fails**

Stop presenting the result as registry data. The current UI can show local sample results if the backend is unreachable. State clearly: “The registry service is unavailable, so this screen is showing illustrative sample data; I will not interpret it as a live registry search.” Resume only after the service is restored.

### 11. Reviewer Copilot and human decision

**Say**

“Reviewer Copilot prepares an officer-facing dossier for a request ID. It can bring together the recommendation, compliance flags, activity-fit information, similar names, and draft bilingual administrative comments. The officer can edit the comments and record a decision.”

**Do**

1. Open **Reviewer Copilot**.
2. Load the request ID prepared before the meeting or navigate from a validation request that generated a brief.
3. Review the recommendation, flags, top similar names, and draft comments.
4. Demonstrate editing the draft comments.
5. If using a disposable test request, record one decision—approve, reject, return, or refer to the committee—and show the confirmation.

**Say**

“The recommendation is decision support. The recorded action is the human reviewer's choice. For the demo, I’m recording a decision only on a test request.”

**Negative path**

If the ID has no brief, show the not-found behavior and explain that the brief must be generated/configured for that request. Do not imply that the system can retrieve an arbitrary application record.

### 12. Administration and lexicon governance

**Say**

“The Administration area supports governance of compliance terms. A reviewer can inspect pending proposals, generate possible spelling or evasion variants, and approve or reject proposals. Direct term entry is also available to an authorized operator in the intended deployment.”

**Do**

1. Open **Administration**.
2. Show the pending proposal list if populated.
3. If available, demonstrate variant generation with a harmless prepared test term.
4. Point out the approve/reject controls and severity choices.
5. Do not approve, reject, or add a production compliance term during the client demo unless explicitly authorized.

**Say**

“Generated variants are proposals, not policy by themselves. Human governance is important before adding terms to the active compliance lexicon.”

### 13. Settings and AI configuration (optional)

**Say**

“Settings expose configuration for the AI provider and model when enabled in this environment. Runtime behavior depends on the configured endpoint, credentials, and feature flags.”

**Do**

1. Open **Settings** only if the client should see operational configuration.
2. Show status indicators without exposing secrets or editing live credentials.
3. Explain off, shadow, and on modes at a high level:
   - **Off:** the relevant AI stage is disabled.
   - **Shadow:** the stage may run for evaluation/logging but should not drive the user-facing decision.
   - **On:** the configured AI output may participate in the relevant workflow.

**Say**

“AI configuration is environment-specific. The demo does not establish production readiness, model accuracy, or service-level performance.”

### 14. Registration and completion — demo-only

**Presenter note:** This is the highest-risk demo step. Prefer to explain the flow without submitting registration unless using a disposable staging database and the live `/TradeName/Register` response has been verified.

**Say**

“When registration is enabled, the backend rechecks the name and activity before attempting to save, so it does not rely solely on an earlier screen result. For today's demonstration, we will not submit a real application or payment.”

**Do**

- If not explicitly approved to write demo data, stop at the final review screen and do not click a payment/registration action.
- If submission is approved, use a disposable test record and verify the API response and database record afterward.
- If a simulated confirmation appears after an API/network error, label it as simulated and do not call the name registered.

### 15. Closing

**Say**

“To recap, TNIS brings together bilingual input, activity-aware screening, duplicate and similarity checks, compliance signals, candidate suggestions, registry search, and officer review support. The positive path helps identify cases with no configured conflict; the negative paths explain conflicts or uncertainty and guide a next step.

“The service is intended to improve visibility and consistency, while the final decision remains with the authorized reviewer. We welcome your feedback on the workflow, rule configuration, activity catalogue, and the evidence an officer needs to make a decision.”

## Positive and negative case matrix

Use only prepared, verified test records. The expected result in this table is the behavior to demonstrate, not a guarantee that a particular example will produce that result in every environment.

| Case | Demo input/setup | Expected behavior to explain |
|---|---|---|
| Positive: no configured conflict | Distinctive bilingual name; valid activity; no matching active/reserved record or compliance flag | May return `OK` and/or suggestions. Explain that this means no configured issue was found, not final approval. |
| Negative: exact duplicate | Known active/reserved name in selected activity | Duplicate conflict should be surfaced and registration should be refused by a live backend check. |
| Negative: reused base name | Known name sharing a distinctive base name in the same activity | A reserved-base-name conflict may block the request. Result depends on extraction and indexed data. |
| Negative/review: confusing similarity | Prepared close spelling/phonetic match | Similar-name signal can request review; it is not automatically equivalent to an exact duplicate. |
| Negative/review: generic or uncertain | Name consists mainly of common descriptors or base-name confidence is low | `NEEDS_REVIEW` may be returned rather than an automatic pass. |
| Negative: restricted term | Prepared fixture mapped to a blocking lexicon category | Show the returned compliance reason and severity; a review-severity term may request review instead of blocking. |
| Review: activity mismatch | Prepared name/activity mismatch supported by configured rules or model | Show a mismatch signal, suggested activity, or clarification request if returned. |
| Validation error: unknown category | Invalid activity category ID | API should reject the request as invalid; correct the category before retrying. |
| Validation error: missing activity | No valid category for an activity-scoped availability check | Explain that a valid category is needed; do not portray missing context as available. |
| Reviewer brief not found | Request ID without a generated/stored brief | Show the not-found response; use a prepared request ID for the positive Copilot path. |
| Backend unavailable | Disconnect or use a deliberately unavailable environment only if appropriate | Do not treat client-side sample search or simulated registration as live registry outcomes. Disclose and stop the affected demo step. |

## Demo wrap-up checklist

- [ ] Every demonstrated registry result came from a successful backend response.
- [ ] The activity category and fixture status were confirmed before interpreting an outcome.
- [ ] Any AI-dependent output was described as configuration-dependent.
- [ ] No real applicant data, production lexicon changes, or real registration/payment was submitted.
- [ ] Any prototype, sample, fallback, or simulated behavior was explicitly identified.
- [ ] Client questions and requested policy/configuration changes were captured for follow-up.

## Technical reference for the presenter

- Main applicant/reservation UI: `frontend/src/components/TradeNameReservationFlow.jsx`
- Compliance form and presets: `frontend/src/components/ValidationTab.jsx`
- Registry search and local fallback behavior: `frontend/src/components/RegistrySearchTab.jsx`
- Reviewer dossier and decision actions: `frontend/src/components/ReviewerCopilotTab.jsx`
- Lexicon administration: `frontend/src/components/LexiconTab.jsx`
- Validation, existence, search, reviewer, and registration endpoints: `backend/api/routes/trade_name.py`
- Base-name uniqueness plan and illustrative cases: `docs/TRADE_NAME_UNIQUENESS_AND_SUGGESTIONS_PLAN.md`
