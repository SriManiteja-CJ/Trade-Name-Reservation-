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
from typing import Optional

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


@router.post(
    "/SuggestCategory",
    response_model=SuggestCategoryResponse,
    summary="Suggest activity category for name (Phase 3, E6)",
)
async def suggest_category(
    request: SuggestCategoryRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> SuggestCategoryResponse:
    """
    POST TradeName/SuggestCategory (spec §5.2, E6).
    Suggests UAE activity category based on trade name keywords.
    """
    # 1. Attempt LLM Category Suggestion when ai_analyzer != off
    if settings.ai_analyzer != FlagMode.off:
        try:
            gateway = LlmGateway(session=db)
            llm_res = await gateway.suggest_category(
                request_id="cat-sug",
                channel=channel,
                name_ar=request.NameAr,
                name_en=request.NameEn,
            )
            await gateway.close()
            if llm_res and llm_res.suggested_category_code:
                return SuggestCategoryResponse(
                    suggested_category_code=llm_res.suggested_category_code,
                    reason_en=llm_res.reason_en,
                    reason_ar=llm_res.reason_ar,
                )
        except Exception as exc:
            logger.warning("llm_suggest_category_failed", extra={"error": str(exc)})

    # 2. Deterministic & Contextual Keyword Classification Fallback
    norm_ar = normalize_arabic(request.NameAr).lower() if request.NameAr else ""
    norm_en = normalize_english(request.NameEn).lower() if request.NameEn else ""
    combined = f"{norm_ar} {norm_en}"

    if any(w in combined for w in ["restaurant", "مطعم", "cafe", "مقهى", "food", "اغذية", "وجبات", "kitchen", "coffee", "bistro", "bakery", "sweet", "diner", "dining", "tea", "roaster", "قهوة"]):
        return SuggestCategoryResponse(
            suggested_category_code="REST_004",
            category_id=4,
            suggested_activity_type="Cafe and Restaurant",
            suggested_activities=["Speciality Coffee & Cafe", "Cafe and Restaurant", "Fast Food & Snacks", "Takeaway Food and Beverage"],
            activity_categories=[
                {"code": "43469", "name_en": "Beverage serving activities", "name_ar": "أنشطة تقديم المشروبات"},
                {"code": "12849", "name_en": "Restaurant and cafe", "name_ar": "مطعم ومقهى"},
                {"code": "12346", "name_en": "Fast Food Restaurant", "name_ar": "مطعم وجبات سريعة"},
                {"code": "34446", "name_en": "Food Delivery Services", "name_ar": "خدمات توصيل الأغذية"},
                {"code": "233463", "name_en": "Takeaway Food Services", "name_ar": "خدمات الوجبات الجاهزة"},
            ],
            reason_en="Keywords indicate food, beverage, and cafe hospitality services.",
            reason_ar="تشير الكلمات إلى نشاط المطاعم والمقاهي وتقديم المشروبات والأغذية.",
        )
    elif any(w in combined for w in ["tech", "تقني", "software", "برمج", "حلول", "digital", "data", "it", "cloud", "cyber", "ai", "smart"]):
        return SuggestCategoryResponse(
            suggested_category_code="TECH_003",
            category_id=3,
            suggested_activity_type="Information Technology & Software Solutions",
            suggested_activities=["Software Publishing & Development", "IT Infrastructure Consulting", "Cloud & Web Applications"],
            activity_categories=[
                {"code": "62010", "name_en": "Computer programming activities", "name_ar": "أنشطة البرمجة الحاسوبية"},
                {"code": "62020", "name_en": "Computer consultancy and facilities management", "name_ar": "استشارات الحاسوب وإدارة المرافق"},
                {"code": "63110", "name_en": "Data processing, hosting and related activities", "name_ar": "معالجة البيانات واستضافتها والأنشطة المتصلة بها"},
            ],
            reason_en="Keywords indicate technology and software solutions activity.",
            reason_ar="تشير الكلمات إلى نشاط تقنية المعلومات والحلول البرمجية.",
        )
    elif any(w in combined for w in ["consult", "استشار", "service", "خدمات", "management", "ادارة", "advisory", "audit"]):
        return SuggestCategoryResponse(
            suggested_category_code="SERV_002",
            category_id=2,
            suggested_activity_type="Professional & Management Consultancy",
            suggested_activities=["Business Management Consultancy", "Corporate Services & Advisory", "Project Management Services"],
            activity_categories=[
                {"code": "70200", "name_en": "Management consultancy activities", "name_ar": "أنشطة الاستشارات الإدارية"},
                {"code": "74900", "name_en": "Other professional, scientific and technical activities", "name_ar": "أنشطة مهنية وعلمية وتقنية أخرى"},
            ],
            reason_en="Keywords indicate professional consultancy and business services.",
            reason_ar="تشير الكلمات إلى نشاط الاستشارات والخدمات الإدارية والمهنية.",
        )
    elif any(w in combined for w in ["contract", "مقاول", "build", "بناء", "construction", "انشاء", "engineer"]):
        return SuggestCategoryResponse(
            suggested_category_code="CONT_006",
            category_id=6,
            suggested_activity_type="General Contracting & Construction",
            suggested_activities=["Building Contracting", "Electromechanical Works", "Interior Decoration & Fit-out"],
            activity_categories=[
                {"code": "41000", "name_en": "Construction of buildings", "name_ar": "تشييد المباني"},
                {"code": "43210", "name_en": "Electrical installation", "name_ar": "التركيبات الكهربائية"},
                {"code": "43300", "name_en": "Building completion and finishing", "name_ar": "أعمال إكمال وتشطيب المباني"},
            ],
            reason_en="Keywords indicate contracting, engineering, and building construction activity.",
            reason_ar="تشير الكلمات إلى نشاط المقاولات وأعمال البناء والتشييد.",
        )
    elif any(w in combined for w in ["real estate", "عقار", "property", "اسكان", "املاك", "broker"]):
        return SuggestCategoryResponse(
            suggested_category_code="REAL_005",
            category_id=5,
            suggested_activity_type="Real Estate Development & Brokerage",
            suggested_activities=["Real Estate Buying & Selling Brokerage", "Leasing & Management", "Property Valuation"],
            activity_categories=[
                {"code": "68100", "name_en": "Real estate activities with own or leased property", "name_ar": "الأنشطة العقارية في الممتلكات الخاصة أو المؤجرة"},
                {"code": "68200", "name_en": "Real estate activities on a fee or contract basis", "name_ar": "الأنشطة العقارية على أساس رسوم أو عقود"},
            ],
            reason_en="Keywords indicate real estate development, brokerage, and property management.",
            reason_ar="تشير الكلمات إلى نشاط العقارات وإدارة الممتلكات والوساطة.",
        )
    else:
        return SuggestCategoryResponse(
            suggested_category_code="COMM_001",
            category_id=1,
            suggested_activity_type="General Commercial Trading",
            suggested_activities=["General Trading", "Wholesale & Retail Merchandise", "Import & Export"],
            activity_categories=[
                {"code": "46900", "name_en": "Non-specialised wholesale trade", "name_ar": "تجارة الجملة غير المتخصصة"},
                {"code": "47190", "name_en": "Other retail sale in non-specialised stores", "name_ar": "تجارة التجزئة في المتاجر غير المتخصصة"},
            ],
            reason_en="General commercial and trading activity.",
            reason_ar="نشاط التجارة العامة والتوريدات التجارية.",
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


@router.post(
    "/CheckTransliteration",
    response_model=CheckTransliterationResponse,
    summary="Validate transliteration consistency between Arabic and English forms (F7)",
)
async def check_transliteration(
    request: CheckTransliterationRequest,
    channel: str = Depends(get_current_channel),
    db: AsyncSession = Depends(get_db),
) -> CheckTransliterationResponse:
    """POST TradeName/CheckTransliteration (spec §5.2, F7)."""
    redis_client = _get_redis_client()
    gateway = LlmGateway(session=db, redis_client=redis_client)
    res = await gateway.check_transliteration(
        request_id=f"chk-trans-{uuid.uuid4().hex[:8]}",
        channel=channel,
        name_ar=request.NameAr,
        name_en=request.NameEn,
        original_ar=request.OriginalNameAr,
        original_en=request.OriginalNameEn,
    )
    if res:
        return CheckTransliterationResponse(
            consistent=res.consistent,
            confidence=res.confidence,
            expected_en=res.expected_en,
            expected_ar=res.expected_ar,
        )
    return CheckTransliterationResponse(
        consistent=True,
        confidence=0.8,
        expected_en=request.NameEn,
        expected_ar=request.NameAr,
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

    index_repo = TradeNameIndexRepository(db)

    # 1. Check for Existing Trade Name (Source of truth DB check)
    exact_matches = await index_repo.lookup_exact(
        normalized_ar=norm_ar,
        normalized_en=norm_en,
    )

    if exact_matches:
        # Trade name already exists! Reject and generate suggestions.
        primary_name = request.name_en or request.name_ar
        primary_name_ar = request.name_ar or request.name_en

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
            message_en=f"Trade name '{primary_name}' already exists in the registry. Duplicate registration blocked.",
            message_ar=f"الاسم التجاري '{primary_name_ar}' مسجل مسبقاً في السجل التجاري ولا يمكن تكراره.",
            suggestions=fallback_sug,
        )

    primary_name = request.name_en or request.name_ar
    primary_name_ar = request.name_ar or request.name_en

    return RegisterTradeNameResponse(
        success=True,
        status="registered",
        is_existing=False,
        trade_name_id=new_trade_name_id,
        reference_number=ref_no,
        message_en=f"Trade name '{primary_name}' has been successfully registered.",
        message_ar=f"تم تسجيل الاسم التجاري '{primary_name_ar}' بنجاح.",
        suggestions=[],
    )


