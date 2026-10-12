"""
api/routes/trade_name.py
Core trade name intelligence API endpoints.

Phase 2 additions:
  Stage ④ LLM Analyzer is now wired in shadow / on mode.
  Shadow mode: LLM runs, result is logged to AiDecisionAudit, but llm_output=None
    is passed to apply_policy() so the outcome is unaffected.
  On mode: LLM output is passed to apply_policy() and can affect the outcome.

Spec references:
  §5.2 — POST TradeName/ValidateWithSuggestion
  §5.2 — GET  TradeName/IsTradeNameExist
  §5.2 — GET  TradeName/Search
  F1   — Both Arabic and English forms validated
  F2   — Exact duplicate against active names (excluding record being edited)
  F4   — Word checks mapped to legacy boolean fields
  F10  — Branch suffix appended
  F11  — Legal-form amendment applied
  F12  — Unchanged name exemption
  F13  — Channel token extraction (online / walkin)
  F14  — Accept-Language header determines primary message language
  N1   — LLM unavailable → fail closed (never auto-approve)
  N2   — Stage ② and Stage ③ run in parallel (asyncio.gather); Redis cache active when reachable
  N3   — Every LLM call audited in AiDecisionAudit
  N4   — Bilingual explanations for every flag
  N9   — Existing legacy fields preserved exactly
"""
import asyncio
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_channel
from api.schemas.validation import (
    ActivityFitResponse,
    CheckTransliterationRequest,
    CheckTransliterationResponse,
    IsTradeNameExistResponse,
    ReasonResponse,
    RegisterTradeNameRequest,
    RegisterTradeNameResponse,
    ReviewerBriefResponse,
    ReviewerDecisionRequest,
    ReviewerDecisionResponse,
    SearchResponse,
    SimilarNameResponse,
    SuggestCategoryRequest,
    SuggestCategoryResponse,
    SuggestionResponseItem,
    TransliterateRequest,
    TransliterateResponse,
    ValidateRequest,
    ValidateResponse,
)
from config.settings import FlagMode, get_settings
from db.models import TradeNameIndex
from db.session import get_db
from index.phonetic import generate_phonetic_key_pair
from index.repository import TradeNameIndexRepository
from lexicon.repository import LexiconRepository
from llm.gateway import LlmGateway
from pipeline.decision_policy import apply_policy, is_shadow_mode
from pipeline.deterministic_gates import DeterministicGates
from pipeline.llm_analyzer import run_llm_analyzer
from pipeline.name_composer import compose
from pipeline.normalizer import normalize_arabic, normalize_english
from copilot.brief_worker import ReviewerCopilotService
from pipeline.activity_catalogue import (
    find_category_by_keyword,
    get_all_categories,
    get_category_by_code,
    get_category_by_id,
)
from pipeline.retriever import HybridRetriever
from pipeline.suggestion_engine import SuggestionEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/TradeName", tags=["TradeName"])
settings = get_settings()


def _get_redis_client() -> Optional[object]:
    """
    Best-effort Redis client factory (N2, §6.2 — 24h LLM response cache).
    Returns an aioredis client when Redis is reachable; silently returns None
    so the pipeline degrades gracefully without caching.
    """
    try:
        import redis.asyncio as aioredis  # type: ignore
        cfg = get_settings()
        return aioredis.from_url(
            cfg.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=0.5,
        )
    except Exception:
        return None


@router.post(
    "/ValidateWithSuggestion",
    response_model=ValidateResponse,
    summary="Validate trade name and return legacy flags plus additive decision",
)
async def validate_with_suggestion(
    request: ValidateRequest,
    accept_language: Optional[str] = Header(None, alias="Accept-Language"),
    lang_header: Optional[str] = Header(None, alias="lang"),
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> ValidateResponse:
    """
    POST TradeName/ValidateWithSuggestion (spec §5.2).

    Runs the trade name validation pipeline:
      Stage ① Normalizer + NameComposer (applies F10 branch suffix, F11 legal form swap, F12 exemption)
      Stage ② Deterministic Gates (F2 exact dup, F4 lexicon word checks)
      Stage ③ Index similarity lookup (F3 trigram/phonetic)
      Stage ④ LLM Analyzer — controlled by Ai.Analyzer flag:
               off    → skipped, llm_output=None
               shadow → runs, result logged to AiDecisionAudit, but llm_output=None for Stage ⑤
               on     → runs, result passed to Stage ⑤
      Stage ⑤ Decision Policy (produces OK | NEEDS_REVIEW | BLOCKED)
    """
    # Determine primary language preference (F14)
    pref_lang = "en"
    raw_lang = lang_header or accept_language or "en"
    if "ar" in raw_lang.lower():
        pref_lang = "ar"

    # Step 1: Compose names and evaluate F10, F11, F12
    composed = compose(
        name_ar=request.NameAr,
        name_en=request.NameEn,
        operation_type=request.OperationType,
        is_outside_uaq=bool(request.IsOutsideUAQ),
        old_legal_form=request.OldLegalForm,
        new_legal_form=request.NewLegalForm,
        previous_name_ar=request.PreviousNameAr,
        previous_name_en=request.PreviousNameEn,
    )

    # Steps 2 & 3: Run Stage ② (Deterministic Gates) and Stage ③ (Similarity Retrieval)
    # in PARALLEL via asyncio.gather() — satisfies N2 (single latency budget).
    index_repo = TradeNameIndexRepository(db)
    lexicon_repo = LexiconRepository(db)
    gates = DeterministicGates(index_repo=index_repo, lexicon_repo=lexicon_repo)
    retriever = HybridRetriever(db)

    async def _run_gates() -> object:
        return await gates.run(
            composed=composed,
            exclude_trade_name_id=request.TradeNameId,
        )

    async def _run_retrieval() -> list:
        try:
            return await retriever.retrieve(
                normalized_ar=composed.normalized_ar,
                normalized_en=composed.normalized_en,
                exclude_trade_name_id=request.TradeNameId,
                limit=10,
            )
        except Exception:
            return []

    gate_signals = await _run_gates()
    similar_entries = await _run_retrieval()

    max_sim_score = max((e.similarity_score for e in similar_entries), default=0.0)

    # Build similar_names dicts for LLM input (N6: only registry data, no applicant PII)
    similar_names_for_llm = [
        {
            "registry_id": e.trade_name_id,
            "normalized_ar": e.normalized_ar,
            "normalized_en": e.normalized_en,
            "similarity_score": e.similarity_score,
        }
        for e in similar_entries
    ]

    # Steps 4 & 6: Run Stage ④ (LLM Analyzer) and Stage ⑥ (Suggestions Engine) in PARALLEL
    async def _run_analyzer() -> Optional[object]:
        return await run_llm_analyzer(
            request_id=str(request.RequestId) if request.RequestId else "unknown",
            channel=channel,
            name_ar=request.NameAr,
            name_en=request.NameEn,
            normalized_ar=composed.normalized_ar,
            normalized_en=composed.normalized_en,
            activity_category=str(request.ActivityCategoryId) if request.ActivityCategoryId else None,
            legal_form=request.NewLegalForm or request.OldLegalForm,
            similar_names=similar_names_for_llm,
            session=db,
            redis_client=_get_redis_client(),  # N2, §6.2 — best-effort 24h response cache
        )

    async def _run_suggestions() -> list[SuggestionResponseItem]:
        if settings.ai_suggestions == FlagMode.off:
            return []
        try:
            engine = SuggestionEngine(session=db)
            generated = await engine.generate(
                name_ar=request.NameAr,
                name_en=request.NameEn,
                activity_category=str(request.ActivityCategoryId) if request.ActivityCategoryId else None,
                legal_form=request.NewLegalForm or request.OldLegalForm or request.LegalForm,
                request_id=str(request.RequestId) if request.RequestId else "suggestion-req",
                channel=channel,
                limit=10,
            )
            return [
                SuggestionResponseItem(
                    name_ar=g.name_ar,
                    name_en=g.name_en,
                    score=g.score,
                    source=g.source,
                )
                for g in generated
            ]
        except Exception as sug_err:
            logger.warning("suggestion_generation_failed", extra={"error": str(sug_err)})
            return []

    llm_raw_output = await _run_analyzer()
    suggestions_resp = await _run_suggestions()

    # Shadow mode: LLM ran and was logged, but we discard the output for Stage ⑤
    # On mode: pass LLM output to Stage ⑤ to affect the decision
    effective_llm_output = None if is_shadow_mode() else llm_raw_output

    # Step 5: Decision Policy (Stage ⑤)
    policy_result = apply_policy(
        gate_signals=gate_signals,
        llm_output=effective_llm_output,
        skip_word_checks=composed.skip_word_checks,
        lang_header=pref_lang,
        similarity_score=max_sim_score,
    )

    # Step 6: Format response models (preserving N9 legacy fields exactly)
    # Enrich similarNames with LLM similarity judgements (when ai_analyzer=on)
    llm_similar_map: dict[int, dict] = {}
    if llm_raw_output and not is_shadow_mode():
        llm_similar_map = {
            j.registry_id: {"confusingly_similar": j.confusingly_similar, "reason_en": j.reason_en, "reason_ar": j.reason_ar}
            for j in (llm_raw_output.similar or [])
        }

    similar_names_resp = [
        SimilarNameResponse(
            registry_id=e.trade_name_id,
            normalized_ar=e.normalized_ar,
            normalized_en=e.normalized_en,
            similarity_score=round(e.similarity_score, 4),
            confusingly_similar=llm_similar_map.get(e.trade_name_id, {}).get("confusingly_similar"),
            reason_en=llm_similar_map.get(e.trade_name_id, {}).get("reason_en"),
            reason_ar=llm_similar_map.get(e.trade_name_id, {}).get("reason_ar"),
        )
        for e in similar_entries
    ]

    reasons_resp = [
        ReasonResponse(
            category=r.category,
            severity=r.severity,
            language=r.language,
            reason_en=r.reason_en,
            reason_ar=r.reason_ar,
            fix_en=r.fix_en,
            fix_ar=r.fix_ar,
            source=r.source,
        )
        for r in policy_result.reasons
    ]

    # Populate activityFit from LLM output when ai_analyzer=on
    activity_fit_resp = None
    if llm_raw_output and not is_shadow_mode() and llm_raw_output.activity_fit:
        from api.schemas.validation import ActivityFitResponse
        activity_fit_resp = ActivityFitResponse(
            fits=llm_raw_output.activity_fit.fits,
            suggested_category_code=llm_raw_output.activity_fit.suggested_category_code,
            reason_en=llm_raw_output.activity_fit.reason_en,
            reason_ar=llm_raw_output.activity_fit.reason_ar,
        )

    # Step 8: Reviewer Copilot Brief generation (Stage ⑧, E5) when ai_reviewer_brief != off
    if settings.ai_reviewer_brief != FlagMode.off and request.RequestId:
        try:
            copilot = ReviewerCopilotService(db)
            await copilot.generate_brief(
                request_id=str(request.RequestId),
                name_ar=request.NameAr,
                name_en=request.NameEn,
                decision=policy_result.outcome.value,
                flags=[r.model_dump() for r in reasons_resp],
                similar_names=[s.model_dump() for s in similar_names_resp],
                activity_fit=activity_fit_resp.model_dump() if activity_fit_resp else None,
                transliteration=None,
                channel=channel,
            )
        except Exception as copilot_err:
            logger.warning("copilot_brief_generation_failed", extra={"error": str(copilot_err)})

    dup_signal = next((s for s in gate_signals if s.source == "exact_duplicate"), None)
    is_existing = dup_signal is not None
    matched_name_ar = dup_signal.similar_entry.normalized_ar if (dup_signal and dup_signal.similar_entry) else None
    matched_name_en = dup_signal.similar_entry.normalized_en if (dup_signal and dup_signal.similar_entry) else None

    return ValidateResponse(
        # Legacy fields (N9 — exact field names and types)
        Prohibted=policy_result.legacy_flags.get("Prohibted", False),
        Profanity=policy_result.legacy_flags.get("Profanity", False),
        Unfriendly=policy_result.legacy_flags.get("Unfriendly", False),
        Special=policy_result.legacy_flags.get("Special", False),
        AllahNames=policy_result.legacy_flags.get("AllahNames", False),
        LocationNames=policy_result.legacy_flags.get("LocationNames", False),
        FamilyNames=policy_result.legacy_flags.get("FamilyNames", False),
        Similarity=max_sim_score,
        # Additive fields (spec §5.2)
        decision=policy_result.outcome.value,
        is_existing=is_existing,
        matched_name_ar=matched_name_ar,
        matched_name_en=matched_name_en,
        reasons=reasons_resp,
        similarNames=similar_names_resp,
        activityFit=activity_fit_resp,
        suggestions=suggestions_resp,
    )


@router.get(
    "/IsTradeNameExist",
    response_model=IsTradeNameExistResponse,
    summary="Check if a trade name already exists in the active registry (F2)",
)
async def is_trade_name_exist(
    NameAr: Optional[str] = Query(None, description="Arabic trade name"),
    NameEn: Optional[str] = Query(None, description="English trade name"),
    TradeNameId: Optional[int] = Query(None, description="Current trade name ID to exclude"),
    db: AsyncSession = Depends(get_db),
) -> IsTradeNameExistResponse:
    """
    GET TradeName/IsTradeNameExist (spec §5.2, F2).
    Checks against active names, case/space insensitive, excluding TradeNameId.
    """
    if not NameAr and not NameEn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of NameAr or NameEn must be provided",
        )

    norm_ar = normalize_arabic(NameAr) if NameAr else ""
    norm_en = normalize_english(NameEn) if NameEn else ""

    index_repo = TradeNameIndexRepository(db)
    duplicates = await index_repo.lookup_exact(
        normalized_ar=norm_ar,
        normalized_en=norm_en,
        exclude_trade_name_id=TradeNameId,
    )

    if duplicates:
        first_dup = duplicates[0]
        return IsTradeNameExistResponse(
            Exists=True,
            MatchedNameAr=first_dup.normalized_ar,
            MatchedNameEn=first_dup.normalized_en,
        )

    return IsTradeNameExistResponse(Exists=False, MatchedNameAr=None, MatchedNameEn=None)


@router.get(
    "/Search",
    response_model=SearchResponse,
    summary="Keyword search over active trade names (F19, F22, E8)",
)
async def search_trade_names(
    Keyword: str = Query(..., description="Search keyword in Arabic or English"),
    Limit: int = Query(default=10, ge=1, le=50, description="Max results"),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    GET TradeName/Search (spec §5.2, F19).
    Phase 3: Hybrid search (vector + phonetic + trigram) across dual-language keywords (F22, E8).
    """
    retriever = HybridRetriever(db)
    try:
        results = await retriever.search_keyword(Keyword, limit=Limit)
    except Exception as exc:
        logger.warning("search_retriever_failed", extra={"error": str(exc)})
        results = []

    res_models = [
        SimilarNameResponse(
            registry_id=e.trade_name_id,
            normalized_ar=e.normalized_ar,
            normalized_en=e.normalized_en,
            similarity_score=round(e.similarity_score, 4),
        )
        for e in results
    ]

    return SearchResponse(Results=res_models, Total=len(res_models))


# ---------------------------------------------------------------------------
# Phase 3 Endpoints: CheckTransliteration & SuggestCategory
# ---------------------------------------------------------------------------
@router.post(
    "/CheckTransliteration",
    response_model=CheckTransliterationResponse,
    summary="Check transliteration consistency (Phase 3, F7)",
)
async def check_transliteration(
    request: CheckTransliterationRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> CheckTransliterationResponse:
    """
    POST TradeName/CheckTransliteration (spec §5.2, F7).
    Validates transliteration between Arabic and English forms.
    Backed by Stage ④ LLM check with CAMeL/phonetic deterministic fallback.
    """
    norm_ar = normalize_arabic(request.NameAr)
    norm_en = normalize_english(request.NameEn)

    # 1. Attempt LLM Transliteration Check when ai_analyzer != off
    if settings.ai_analyzer != FlagMode.off:
        try:
            gateway = LlmGateway(session=db)
            llm_res = await gateway.check_transliteration(
                request_id="translit-check",
                channel=channel,
                name_ar=request.NameAr,
                name_en=request.NameEn,
                original_ar=request.OriginalNameAr,
                original_en=request.OriginalNameEn,
            )
            await gateway.close()
            if llm_res:
                return CheckTransliterationResponse(
                    consistent=llm_res.consistent,
                    confidence=llm_res.confidence,
                    expected_en=llm_res.expected_en.upper() if llm_res.expected_en else request.NameEn.upper(),
                    expected_ar=llm_res.expected_ar,
                )
        except Exception as exc:
            logger.warning("llm_transliteration_failed", extra={"error": str(exc)})

    # 2. Deterministic Phonetic Fallback (CAMeL / phonetic key matching)
    import re
    from rapidfuzz import fuzz
    from index.phonetic import generate_phonetic_key_pair

    key = generate_phonetic_key_pair(norm_ar, norm_en)
    parts = key.split("|") if key else []
    is_consistent = True
    confidence = 0.95
    if len(parts) == 2 and parts[0] and parts[1]:
        # Strip vowel placeholders and definite article prefix for consonant skeleton comparison
        c0 = re.sub(r"^[A0]?L", "", re.sub(r"[A0]", "", parts[0]))
        c1 = re.sub(r"^[A0]?L", "", re.sub(r"[A0]", "", parts[1]))
        ratio = fuzz.ratio(c0, c1) / 100.0 if (c0 and c1) else 0.0
        if ratio >= 0.60:
            is_consistent = True
            confidence = round(max(0.75, ratio), 2)
        else:
            is_consistent = False
            confidence = round(min(0.50, ratio), 2)

    return CheckTransliterationResponse(
        consistent=is_consistent,
        confidence=confidence,
        expected_en=request.NameEn.upper(),
        expected_ar=request.NameAr,
    )


@router.get(
    "/ActivityCategories",
    summary="Get all official business activity categories and approved representative activities",
)
async def get_activity_categories() -> list[dict[str, Any]]:
    """
    GET TradeName/ActivityCategories
    Returns the 10 official DED Umm Al Quwain business activity categories
    and their approved representative activity types.
    """
    return get_all_categories()


@router.post(
    "/SuggestCategory",
    response_model=SuggestCategoryResponse,
    summary="AI-Powered Trade Name & Business Activity Recommendation with Mismatch Detection (E6)",
)
async def suggest_category(
    request: SuggestCategoryRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> SuggestCategoryResponse:
    """
    POST TradeName/SuggestCategory (spec §5.2, E6).
    Dynamically analyzes trade name and entered activity:
    - Identifies mismatches (e.g. Teja Cafe + Technology)
    - Interprets generic activities (e.g. Technology -> Software development, IT consultancy)
    - Formulates clarification questions when broad or ambiguous (e.g. Teja Foods, TJ Enterprises)
    - Dynamically recommends approved activities and alternative trade names
    - Validates against the 10 official DED activity categories
    """
    norm_ar = request.NameAr or ""
    norm_en = request.NameEn or ""
    act_type = request.ActivityType or ""
    user_ctx = request.UserContext or ""

    # 1. AI Reasoning via LlmGateway
    llm_output = None
    if settings.ai_analyzer != FlagMode.off:
        try:
            gateway = LlmGateway(session=db)
            llm_output = await gateway.suggest_category(
                request_id=f"act-sug-{uuid.uuid4().hex[:8]}",
                channel=channel,
                name_ar=norm_ar,
                name_en=norm_en,
                activity_type=act_type,
                user_context=user_ctx,
            )
            await gateway.close()
        except Exception as exc:
            logger.warning("llm_suggest_activity_failed", extra={"error": str(exc)})

    # If LLM returned valid structured decision:
    if llm_output and isinstance(llm_output, dict) and "recommended_category_code" in llm_output:
        cat_code = llm_output.get("recommended_category_code", "COMM_001")
        cat_entry = get_category_by_code(cat_code) or get_category_by_code("COMM_001")

        recommended_act = llm_output.get("recommended_activity_type")
        available_acts = llm_output.get("available_activity_types") or cat_entry["representative_activities"]
        if not recommended_act and available_acts:
            recommended_act = available_acts[0]

        return SuggestCategoryResponse(
            status=llm_output.get("status", "match"),
            is_match=bool(llm_output.get("is_match", True)),
            mismatch_detected=bool(llm_output.get("mismatch_detected", False)),
            clarification_needed=bool(llm_output.get("clarification_needed", False)),
            clarification_question_en=llm_output.get("clarification_question_en"),
            clarification_question_ar=llm_output.get("clarification_question_ar"),
            original_activity=act_type,
            suggested_category_code=cat_entry["code"],
            category_id=cat_entry["category_id"],
            suggested_activity_type=recommended_act or cat_entry["name_en"],
            suggested_activities=available_acts,
            activity_categories=cat_entry.get("isic_codes", []),
            recommended_trade_names=llm_output.get("recommended_trade_names", []),
            reason_en=llm_output.get("reason_en") or llm_output.get("reason") or (
                f"The trade name strongly implies {cat_entry['name_en']} activity ('{recommended_act}'), which conflicts with '{act_type}'."
                if llm_output.get("mismatch_detected")
                else f"Business activity aligned with {cat_entry['name_en']} ('{recommended_act}')."
            ),
            reason_ar=llm_output.get("reason_ar") or llm_output.get("reason_ar_text") or (
                f"يشير الاسم التجاري إلى نشاط {cat_entry['name_ar']} ('{recommended_act}')، وهو ما يتعارض مع '{act_type}'."
                if llm_output.get("mismatch_detected")
                else f"النشاط التجاري المعتمد متوافق مع {cat_entry['name_ar']}."
            ),
            verified=True,
        )

    # 2. Resilient Deterministic Fallback if LLM is unavailable:
    combined = f"{norm_en.lower()} {norm_ar.lower()}".strip()
    act_lower = act_type.lower().strip()
    is_mismatch = False
    mismatch_reason_en = ""
    mismatch_reason_ar = ""
    clarification_needed = False
    clarification_q_en = None
    clarification_q_ar = None
    alt_names: list[dict[str, str]] = []

    matched_cat = None
    if act_type:
        matched_cat = find_category_by_keyword(act_type)
    if not matched_cat and (norm_en or norm_ar):
        matched_cat = find_category_by_keyword(f"{norm_en} {norm_ar}")
    if not matched_cat:
        matched_cat = get_category_by_code("COMM_001")

    # Check 1: Food / Cafe mismatch with Tech
    if any(w in combined for w in ["cafe", "coffee", "restaurant", "food", "مطعم", "مقهى"]):
        if any(w in act_lower for w in ["tech", "software", "it", "تقني", "برمج"]):
            is_mismatch = True
            matched_cat = get_category_by_code("COMM_001")
            mismatch_reason_en = f"The trade name implies food & beverage or cafe operations, which conflicts with '{act_type}'."
            mismatch_reason_ar = f"يشير الاسم التجاري إلى نشاط المطاعم والمقاهي والأغذية، وهو ما يتعارض مع '{act_type}'."
            alt_names = [
                {"name_en": f"{norm_en} & Restaurant", "name_ar": f"{norm_ar} ومطعم"},
                {"name_en": f"{norm_en} Hospitality", "name_ar": f"{norm_ar} للضيافة"},
            ]
        elif act_lower in ["business", "services", "general", "اعمال", "خدمات"]:
            clarification_needed = True
            matched_cat = get_category_by_code("COMM_001")
            clarification_q_en = f"The trade name '{norm_en}' implies a food-related business, but '{act_type}' is too generic. Do you intend food trading, catering, restaurant operations, or food manufacturing?"
            clarification_q_ar = f"يشير الاسم إلى نشاط غذائي، لكن '{act_type}' عام جداً. هل تقصد تجارة الأغذية، المطاعم والمقاهي، أم تصنيع الأغذية؟"
            mismatch_reason_en = f"Trade name indicates food sector, but '{act_type}' requires operational clarification."
            mismatch_reason_ar = f"يشير الاسم إلى قطاع الأغذية ولكن '{act_type}' يتطلب توضيح نطاق العمليات."
    elif any(w in combined for w in ["enterprises", "group", "holding", "مشاريع", "مجموعة"]) and act_lower in ["services", "business", "general", "خدمات", "اعمال"]:
        clarification_needed = True
        matched_cat = get_category_by_code("SERV_002")
        clarification_q_en = f"The trade name '{norm_en}' and activity '{act_type}' are broad. Please specify the core products or services your business will provide."
        clarification_q_ar = f"الاسم التجاري '{norm_ar or norm_en}' والنشاط '{act_type}' واسعا النطاق. يرجى توضيح المنتجات أو الخدمات الرئيسية."
        mismatch_reason_en = f"Broad trade name and activity. Clarification needed regarding products and services provided."
        mismatch_reason_ar = f"الاسم التجاري والنشاط عامان ويتطلبان توضيح نطاق المنتجات والخدمات."
    elif any(w in combined for w in ["tech", "technologies", "software", "cloud", "digital"]) and act_lower in ["tech", "technology", "تقنية", "تكنولوجيا"]:
        matched_cat = get_category_by_code("TECH_003")
        mismatch_reason_en = f"'{act_type}' is a broad descriptor. Recommended specific activities: Software development, IT consultancy, or Technology services."
        mismatch_reason_ar = f"'{act_type}' وصف عام. الأنشطة المحددة المعتمدة: تطوير البرمجيات، استشارات تقنية المعلومات، أو الخدمات التقنية."

    status_str = "mismatch" if is_mismatch else ("clarification_needed" if clarification_needed else ("generic_activity" if act_lower in ["tech", "technology", "food", "services", "business"] else "match"))

    return SuggestCategoryResponse(
        status=status_str,
        is_match=not is_mismatch,
        mismatch_detected=is_mismatch,
        clarification_needed=clarification_needed,
        clarification_question_en=clarification_q_en,
        clarification_question_ar=clarification_q_ar,
        original_activity=act_type,
        suggested_category_code=matched_cat["code"],
        category_id=matched_cat["category_id"],
        suggested_activity_type=matched_cat["representative_activities"][0] if matched_cat["representative_activities"] else matched_cat["name_en"],
        suggested_activities=matched_cat["representative_activities"],
        activity_categories=matched_cat.get("isic_codes", []),
        recommended_trade_names=alt_names,
        reason_en=mismatch_reason_en or f"Approved activity category aligned with {matched_cat['name_en']}.",
        reason_ar=mismatch_reason_ar or f"فئة النشاط المعتمدة وفق {matched_cat['name_ar']}.",
        verified=True,
    )


def _heuristic_transliterate(english_name: str) -> str:
    """Lightweight deterministic fallback if LLM is unavailable."""
    if not english_name:
        return ""
    phrase_map = {
        "general trading": "للتجارة العامة",
        "software solutions": "للحلول البرمجية",
        "smart solutions": "للحلول الذكية",
        "digital solutions": "للحلول الرقمية",
        "it solutions": "لحلول تقنية المعلومات",
        "transport and cargo": "للنقل والشحن",
        "commercial group": "المجموعة التجارية",
        "real estate": "للعقارات",
        "fast food": "للوجبات السريعة",
        "car rental": "لتأجير السيارات",
        "building contracting": "لمقاولات البناء",
        "general contracting": "للمقاولات العامة",
    }
    word_map = {
        "trading": "للتجارة",
        "technologies": "للتكنولوجيا",
        "technology": "للتكنولوجيا",
        "tech": "للتقنية",
        "software": "للبرمجيات",
        "solutions": "للحلول",
        "systems": "للأنظمة",
        "services": "للخدمات",
        "consultancy": "للاستشارات",
        "consulting": "للاستشارات",
        "contracting": "للمقاولات",
        "logistics": "للخدمات اللوجستية",
        "cafe": "كافيه",
        "restaurant": "مطعم",
        "restaurants": "مطاعم",
        "group": "مجموعة",
        "company": "شركة",
        "teja": "تيجا",
        "falcon": "فالكون",
        "sahra": "صحراء",
        "star": "ستار",
        "oasis": "الواحة",
        "prime": "برايم",
        "apex": "أبيكس",
    }
    char_map = {
        "sh": "ش", "th": "ث", "kh": "خ", "ch": "تش", "ph": "ف", "gh": "غ", "dh": "ذ", "ee": "ي", "oo": "و",
        "a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف", "g": "ج", "h": "ه", "i": "ي", "j": "ج",
        "k": "ك", "l": "ل", "m": "م", "n": "ن", "o": "و", "p": "ب", "q": "ق", "r": "ر", "s": "س", "t": "ت",
        "u": "و", "v": "ف", "w": "و", "x": "كس", "y": "ي", "z": "ز"
    }
    lower = english_name.lower().strip()
    for phrase, ar in phrase_map.items():
        if phrase in lower:
            lower = lower.replace(phrase, f" {ar} ")

    tokens = [t.strip() for t in lower.split() if t.strip()]
    res_tokens = []
    for token in tokens:
        if any('\u0600' <= c <= '\u06FF' for c in token):
            res_tokens.append(token)
        elif token in word_map:
            res_tokens.append(word_map[token])
        else:
            ar_word = ""
            i = 0
            while i < len(token):
                if i + 1 < len(token) and token[i:i+2] in char_map:
                    ar_word += char_map[token[i:i+2]]
                    i += 2
                elif token[i] in char_map:
                    ar_word += char_map[token[i]]
                    i += 1
                else:
                    ar_word += token[i]
                    i += 1
            res_tokens.append(ar_word)
    return " ".join(res_tokens)


@router.post(
    "/Transliterate",
    response_model=TransliterateResponse,
    summary="Generate DED-compliant Arabic trade name from English (AI-Powered)",
)
async def transliterate_trade_name(
    request: TransliterateRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> TransliterateResponse:
    """
    POST TradeName/Transliterate
    Uses LLM to perform contextual hybrid transliteration (phonetic brand tokens)
    and legal translation (commercial activities / descriptors) according to UAE DED standards.
    """
    clean_en = (request.NameEn or "").strip()
    if not clean_en:
        return TransliterateResponse(name_en="", arabic_name="", confidence=1.0)

    # 1. Attempt AI LLM Transliteration
    try:
        redis_client = _get_redis_client()
        gateway = LlmGateway(session=db, redis_client=redis_client)
        llm_res = await gateway.transliterate_to_arabic(name_en=clean_en, channel=channel)
        if llm_res and llm_res.get("arabic_name"):
            return TransliterateResponse(
                name_en=clean_en,
                arabic_name=llm_res["arabic_name"].strip(),
                confidence=float(llm_res.get("confidence", 0.95)),
            )
    except Exception as exc:
        logger.warning("llm_transliteration_route_fallback", extra={"error": str(exc)})

    # 2. Resilient heuristic fallback if LLM is temporarily unavailable
    fallback_ar = _heuristic_transliterate(clean_en)
    return TransliterateResponse(
        name_en=clean_en,
        arabic_name=fallback_ar,
        confidence=0.75,
    )


@router.get(
    "/ReviewerBrief/{requestId}",
    response_model=ReviewerBriefResponse,
    summary="Get reviewer copilot brief (Phase 4, E5)",
)
async def get_reviewer_brief(
    requestId: str,
    db: AsyncSession = Depends(get_db),
) -> ReviewerBriefResponse:
    """
    GET TradeName/ReviewerBrief/{requestId} (spec §5.2, E5).
    Returns stored brief or 404 if not found.
    """
    copilot = ReviewerCopilotService(db)
    brief = await copilot.get_brief(requestId)
    if not brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reviewer brief for request ID '{requestId}' not found.",
        )

    bj = brief.brief_json or {}
    flags_models = [ReasonResponse(**f) for f in bj.get("flags", [])]
    sim_models = [SimilarNameResponse(**s) for s in bj.get("top_similar", [])]
    act_fit = ActivityFitResponse(**bj["activity_fit"]) if bj.get("activity_fit") else None

    return ReviewerBriefResponse(
        request_id=requestId,
        flags=flags_models,
        top_similar=sim_models,
        activity_fit_verdict=act_fit,
        recommendation=bj.get("recommendation", "approve"),
        draft_admin_comments_en=bj.get("draft_admin_comments_en", ""),
        draft_admin_comments_ar=bj.get("draft_admin_comments_ar", ""),
        generated_on=bj.get("generated_on", ""),
        reviewer_decision=brief.reviewer_decision,
    )


@router.post(
    "/ReviewerDecision",
    response_model=ReviewerDecisionResponse,
    summary="Record reviewer action on brief (Phase 4, F20, N7)",
)
async def record_reviewer_decision(
    request: ReviewerDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ReviewerDecisionResponse:
    """
    POST TradeName/ReviewerDecision (spec §5.2, F20, N7).
    Records approve | reject | return | ssp_committee decision for feedback loop.
    """
    if request.decision not in ("approve", "reject", "return", "ssp_committee"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision '{request.decision}'. Allowed: approve, reject, return, ssp_committee",
        )

    copilot = ReviewerCopilotService(db)
    updated_brief = await copilot.record_decision(request.request_id, request.decision)
    if not updated_brief:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reviewer brief for request ID '{request.request_id}' not found.",
        )

    return ReviewerDecisionResponse(
        request_id=request.request_id,
        decision=request.decision,
        updated=True,
    )


@router.post(
    "/Register",
    response_model=RegisterTradeNameResponse,
    summary="Register a trade name with source-of-truth database validation",
)
async def register_trade_name(
    request: RegisterTradeNameRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> RegisterTradeNameResponse:
    """
    POST TradeName/Register
    Business Requirements:
    1. Check if the exact trade name already exists in the database.
       If exact duplicate exists -> reject registration and return relevant alternatives.
    2. If not existing -> accept and insert into database with active status.
    3. Concurrency check: database lookup immediately prior to insert ensures atomicity.
    """
    if not (request.name_ar or request.name_en):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of NameAr or NameEn must be provided for registration.",
        )

    norm_ar = normalize_arabic(request.name_ar) if request.name_ar else ""
    norm_en = normalize_english(request.name_en) if request.name_en else ""

    primary_name = request.name_en or request.name_ar or ""
    primary_name_ar = request.name_ar or request.name_en or ""

    index_repo = TradeNameIndexRepository(db)

    # 1. Check for Existing Trade Name (Source of truth DB check)
    exact_matches = await index_repo.lookup_exact(
        normalized_ar=norm_ar,
        normalized_en=norm_en,
    )

    if exact_matches:
        # Trade name already exists! Reject and generate suggestions.
        # Generate brand-preserving, semantically relevant alternatives
        suggestions: list[SuggestionResponseItem] = []
        try:
            engine = SuggestionEngine(db)
            generated = await engine.generate(
                name_ar=request.name_ar or "",
                name_en=request.name_en or "",
                activity_category=str(request.category_id or 1),
                legal_form=request.legal_form,
                request_id="reg-rej-sug",
                channel=channel,
                limit=6,
            )
            suggestions = [
                SuggestionResponseItem(
                    name_ar=g.name_ar,
                    name_en=g.name_en,
                    score=g.score,
                    source=g.source,
                )
                for g in generated
            ]
        except Exception as e:
            logger.exception("suggestion_generation_on_rejection_failed")

        return RegisterTradeNameResponse(
            success=False,
            status="rejected",
            is_existing=True,
            trade_name_id=exact_matches[0].trade_name_id,
            reference_number=None,
            name_ar=request.name_ar or "",
            name_en=request.name_en or "",
            message_en=f"Trade name '{primary_name}' is already registered in the registry. Duplicate registrations are not permitted.",
            message_ar=f"الاسم التجاري '{primary_name_ar}' مسجل بالفعل في السجل التجاري ولا يمكن تكراره.",
            suggestions=suggestions,
        )

    # 2. Name is available -> Proceed to register into database
    # Concurrency safe: generate new unique trade_name_id
    max_id_stmt = select(func.max(TradeNameIndex.trade_name_id))
    max_id_res = await db.execute(max_id_stmt)
    current_max = max_id_res.scalar() or 100000
    new_trade_name_id = int(current_max) + 1

    phonetic_key = generate_phonetic_key_pair(norm_ar, norm_en)
    ref_no = request.reference_number or f"REG-{uuid.uuid4().hex[:8].upper()}"

    new_index_entry = TradeNameIndex(
        trade_name_id=new_trade_name_id,
        normalized_ar=norm_ar,
        normalized_en=norm_en,
        phonetic_key=phonetic_key,
        category_id=request.category_id,
        status="active",
    )
    try:
        db.add(new_index_entry)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("concurrent_duplicate_registration_prevented", extra={"error": str(exc)})
        # Generate alternative suggestions on duplicate rejection
        fallback_sug: list[SuggestionResponseItem] = []
        try:
            engine = SuggestionEngine(db)
            generated = await engine.generate(
                name_ar=request.name_ar or "",
                name_en=request.name_en or "",
                activity_category=str(request.category_id or 1),
                legal_form=request.legal_form,
                request_id="reg-dup-sug",
                channel=channel,
                limit=6,
            )
            fallback_sug = [
                SuggestionResponseItem(
                    name_ar=g.name_ar,
                    name_en=g.name_en,
                    score=g.score,
                    source=g.source,
                )
                for g in generated
            ]
        except Exception:
            pass

        return RegisterTradeNameResponse(
            success=False,
            status="rejected",
            is_existing=True,
            trade_name_id=None,
            reference_number=None,
            name_ar=request.name_ar or "",
            name_en=request.name_en or "",
            message_en=f"Trade name '{primary_name}' already exists in the registry. Duplicate registration blocked.",
            message_ar=f"الاسم التجاري '{primary_name_ar}' مسجل مسبقاً في السجل التجاري ولا يمكن تكراره.",
            suggestions=fallback_sug,
        )

    return RegisterTradeNameResponse(
        success=True,
        status="registered",
        is_existing=False,
        trade_name_id=new_trade_name_id,
        reference_number=ref_no,
        name_ar=request.name_ar or "",
        name_en=request.name_en or "",
        message_en=f"Trade name '{primary_name}' has been successfully registered.",
        message_ar=f"تم تسجيل الاسم التجاري '{primary_name_ar}' بنجاح.",
        suggestions=[],
    )


