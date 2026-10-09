"""
pipeline/suggestion_engine.py
Stage ⑥ Suggestion Engine for the Trade Name Intelligence Service.

Responsibilities:
  1. Call LLM to draft ~25 bilingual candidate pairs (F8, F9 complementary patterns).
  2. Fall back to deterministic template-based generation if LLM fails (Ambiguity #5).
  3. Batch filter candidates through Stage ① normalizer and Stage ② deterministic gates.
  4. Perform single set-based SQL query to eliminate active/reserved names (F18, N8).
  5. Apply legal-form formatting when required (F8).
  6. Ensure all English suggestion names are returned in UPPER CASE (F17).
  7. Rank and return top 10 distinct, unreserved suggestions (F8).

Spec references:
  F8  — Return up to 10 distinct, unreserved suggestions; include legal form if required
  F9  — Complementary patterns (name + activity wording)
  F17 — English suggestions returned in UPPER CASE
  F18 — Reserved names are never suggested (single set query)
  F21 — Released/expired names can become suggested if clean
  N8  — Bounded cost: small LLM model + single batch DB query
  §3.1 Stage ⑥ — Suggestion Engine architecture
"""
import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import FlagMode, get_settings
from lexicon.repository import LexiconRepository
from llm.gateway import LlmGateway
from pipeline.normalizer import normalize_arabic, normalize_english, strip_tokens

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Template Fallback Library (Ambiguity #5, F9 complementary patterns)
# ---------------------------------------------------------------------------
CATEGORY_NAME_MAP: dict[str, str] = {
    "1": "Commercial & General Trading",
    "2": "Professional Services & Consultancy",
    "3": "Information Technology & Software",
    "4": "Restaurant, Cafe & Dining Services",
    "5": "Real Estate & Property Management",
    "6": "Construction & Contracting",
}

def extract_core_brand_token(name: str, lang: str = "en") -> str:
    """
    Isolates the distinctive brand identifier from common descriptor terms (Requirement 2 & 3).
    e.g. 'Teja Cafe and Restaurant' -> 'Teja'
         'Teja cafe' -> 'Teja'
         'مطعم وكافيه تيجا' -> 'تيجا'
    """
    if not name:
        return ""
    if lang == "en":
        descriptors = {
            "cafe", "café", "restaurant", "restaurants", "bistro", "bistros",
            "diner", "dining", "kitchen", "lounge", "food", "foods", "and", "&",
            "co", "company", "house", "trading", "services", "solutions",
            "tech", "group", "enterprises", "general", "express", "grill",
            "bakery", "sweets", "bar", "hub", "center", "dine"
        }
        tokens = name.strip().split()
        brand_tokens = [w for w in tokens if w.lower() not in descriptors]
        return " ".join(brand_tokens) if brand_tokens else name.strip()
    else:
        descriptors_ar = {
            "مطعم", "كافيه", "مقهى", "لاونج", "بسترو", "مأكولات", "ماكولات",
            "وجبات", "و", "للحلول", "للتجارة", "للخدمات", "شركة", "مؤسسة",
            "العامة", "اكسبريس", "مطبخ", "جريل", "مخبز", "حلويات", "بيت",
            "مركز", "جروب", "داينينغ"
        }
        tokens = name.strip().split()
        brand_tokens = [w for w in tokens if w not in descriptors_ar]
        return " ".join(brand_tokens) if brand_tokens else name.strip()


def transliterate_en_to_ar_token(token: str) -> str:
    """
    Phonetically transliterates an English brand name into Arabic script.
    e.g. 'Teja' -> 'تيجا', 'Noor' -> 'نور'
    """
    if not token:
        return ""
    common_map = {
        "teja": "تيجا",
        "sahra": "صحراء",
        "sahraa": "صحراء",
        "noor": "نور",
        "nour": "نور",
        "al noor": "النور",
        "alnoor": "النور",
        "baraka": "بركة",
        "al baraka": "البركة",
        "albaraka": "البركة",
        "falcon": "فالكون",
        "star": "ستار",
        "al star": "الستار",
        "oasis": "الواحة",
        "marina": "مارينا",
        "delta": "دلتا",
        "prime": "برايم",
        "apex": "أبيكس",
        "crown": "كراون",
        "elite": "إيليت",
        "future": "فيوتشر",
    }
    low = token.lower().strip()
    if low in common_map:
        return common_map[low]

    mapping = {
        "sh": "ش", "th": "ث", "kh": "خ", "ch": "تش", "ph": "ف", "gh": "غ", "dh": "ذ",
        "a": "ا", "b": "ب", "c": "ك", "d": "د", "e": "ي", "f": "ف", "g": "ج",
        "h": "ه", "i": "ي", "j": "ج", "k": "ك", "l": "ل", "m": "م", "n": "ن",
        "o": "و", "p": "ب", "q": "ق", "r": "ر", "s": "س", "t": "ت", "u": "و",
        "v": "ف", "w": "و", "x": "كس", "y": "ي", "z": "ز"
    }
    res = []
    i = 0
    t = low
    while i < len(t):
        if i + 1 < len(t) and t[i:i+2] in mapping:
            res.append(mapping[t[i:i+2]])
            i += 2
        elif t[i] in mapping:
            res.append(mapping[t[i]])
            i += 1
        elif t[i].isspace():
            res.append(" ")
            i += 1
        else:
            i += 1
    return "".join(res).strip()


def transliterate_ar_to_en_token(token: str) -> str:
    """
    Phonetically transliterates an Arabic brand name into Latin/English script.
    e.g. 'تيجا' -> 'Teja', 'صحراء' -> 'Sahra'
    """
    if not token:
        return ""
    common_rev_map = {
        "تيجا": "Teja",
        "صحراء": "Sahra",
        "صحرا": "Sahra",
        "نور": "Noor",
        "النور": "Al Noor",
        "بركة": "Baraka",
        "البركة": "Al Baraka",
        "فالكون": "Falcon",
        "الواحة": "Oasis",
        "مارينا": "Marina",
        "دلتا": "Delta",
        "برايم": "Prime",
    }
    token_str = token.strip()
    if token_str in common_rev_map:
        return common_rev_map[token_str]

    ar_to_en = {
        "ا": "a", "أ": "a", "إ": "e", "آ": "aa", "ب": "b", "ت": "t", "ث": "th",
        "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
        "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
        "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
        "ه": "h", "و": "w", "ي": "y", "ى": "a", "ة": "h", "ء": "a"
    }
    res = []
    for char in token_str:
        if char in ar_to_en:
            res.append(ar_to_en[char])
        elif char.isspace():
            res.append(" ")
    return "".join(res).title().strip()


def is_candidate_relevant(
    cand_en: str,
    cand_ar: str,
    brand_en: str,
    brand_ar: str,
) -> bool:
    """
    Checks if a suggestion candidate is meaningfully related to the user's core brand tokens.
    Rejects suggestions that do not retain or relate to the user's brand name.
    """
    b_en = (brand_en or "").lower().strip()
    b_ar = (brand_ar or "").strip()

    c_en = (cand_en or "").lower().strip()
    c_ar = (cand_ar or "").strip()

    # 1. Direct token or substring match in English
    if b_en and (b_en in c_en or any(token in c_en.split() for token in b_en.split())):
        return True

    # 2. Direct token or substring match in Arabic
    if b_ar and (b_ar in c_ar or any(token in c_ar.split() for token in b_ar.split())):
        return True

    # 3. Transliterated token match
    trans_ar = transliterate_en_to_ar_token(b_en)
    if trans_ar and (trans_ar in c_ar or any(token in c_ar.split() for token in trans_ar.split())):
        return True

    trans_en = transliterate_ar_to_en_token(b_ar).lower()
    if trans_en and (trans_en in c_en or any(token in c_en.split() for token in trans_en.split())):
        return True

    # 4. Fuzzy ratio on brand token
    try:
        from rapidfuzz import fuzz
        if b_en:
            for w in c_en.split():
                if fuzz.ratio(b_en, w) >= 70:
                    return True
        if b_ar:
            for w in c_ar.split():
                if fuzz.ratio(b_ar, w) >= 70:
                    return True
    except Exception:
        pass

    return False


CATEGORY_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "4": [
        ("بسترو وكافيه", "BISTRO AND CAFE"),
        ("كافيه هاوس", "CAFE HOUSE"),
        ("بسترو", "BISTRO"),
        ("فود وكافيه", "FOOD & CAFE"),
        ("كيتشن ولاونج", "KITCHEN & LOUNGE"),
        ("لاونج ومطعم", "LOUNGE & RESTAURANT"),
        ("داينينغ وبسترو", "DINING & BISTRO"),
        ("جورميه كافيه", "GOURMET CAFE"),
        ("بايتس وكافيه", "BITES & CAFE"),
        ("اكسبريس كافيه", "EXPRESS CAFE"),
    ],
    "restaurant": [
        ("بسترو وكافيه", "BISTRO AND CAFE"),
        ("كافيه هاوس", "CAFE HOUSE"),
        ("بسترو", "BISTRO"),
        ("فود وكافيه", "FOOD & CAFE"),
        ("كيتشن ولاونج", "KITCHEN & LOUNGE"),
        ("لاونج ومطعم", "LOUNGE & RESTAURANT"),
        ("داينينغ وبسترو", "DINING & BISTRO"),
        ("جورميه كافيه", "GOURMET CAFE"),
        ("بايتس وكافيه", "BITES & CAFE"),
        ("اكسبريس كافيه", "EXPRESS CAFE"),
    ],
    "3": [
        ("للحلول البرمجية", "SOFTWARE SOLUTIONS"),
        ("للتقنيات الذكية", "SMART TECHNOLOGIES"),
        ("للأنظمة والبرمجيات", "SYSTEMS & SOFTWARE"),
        ("للأمن السيبراني", "CYBER SOLUTIONS"),
        ("للابتكار الرقمي", "DIGITAL INNOVATION"),
        ("للتكنولوجيا", "TECH SOLUTIONS"),
        ("ديجيتال لابز", "DIGITAL LABS"),
    ],
    "1": [
        ("للتجارة العامة", "GENERAL TRADING"),
        ("للتجارة والتوزيع", "TRADING & DISTRIBUTION"),
        ("للاستيراد والتصدير", "IMPORT & EXPORT"),
        ("للمشاريع التجارية", "COMMERCIAL VENTURES"),
        ("جلوبال للتجارة", "GLOBAL TRADING"),
    ],
}

DEFAULT_TEMPLATES: list[tuple[str, str]] = [
    ("للتجارة العامة", "GENERAL TRADING"),
    ("للخدمات والاستشارات", "SERVICES & CONSULTING"),
    ("للمشاريع المتكاملة", "INTEGRATED ENTERPRISES"),
    ("الدولية للحلول", "INTERNATIONAL SOLUTIONS"),
    ("الخليجية للأعمال", "GULF BUSINESS"),
    ("العالمية التجارية", "GLOBAL COMMERCIAL"),
]


@dataclass
class SuggestionItemDTO:
    """One verified suggestion candidate."""
    name_ar: str
    name_en: str
    score: float = 1.0
    source: str = "llm"  # "llm" or "template"


class SuggestionEngine:
    """
    Stage ⑥ Suggestion Engine.
    Generates, screens, filters, and formats trade name alternatives.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Optional[Any] = None,
    ) -> None:
        self.session = session
        self.redis_client = redis_client
        self.lexicon_repo = LexiconRepository(session)

    async def generate(
        self,
        *,
        name_ar: str,
        name_en: str,
        activity_category: Optional[str] = None,
        legal_form: Optional[str] = None,
        request_id: str = "suggestion-req",
        channel: str = "online",
        limit: int = 10,
    ) -> list[SuggestionItemDTO]:
        """
        Generate up to `limit` (default 10 per F8) compliant, unreserved suggestions.

        Returns empty list if ai_suggestions is FlagMode.off.
        """
        if settings.ai_suggestions == FlagMode.off:
            return []

        # Extract core name components
        parsed_ar = strip_tokens(normalize_arabic(name_ar), lang="ar")
        parsed_en = strip_tokens(normalize_english(name_en), lang="en")
        core_ar = parsed_ar.core_name or name_ar
        core_en = parsed_en.core_name or name_en

        brand_en = (extract_core_brand_token(core_en, "en") or core_en).title()
        brand_ar = extract_core_brand_token(core_ar, "ar") or core_ar

        # Reconcile brand tokens across languages (Requirement 6 & 7)
        if not brand_ar and brand_en:
            brand_ar = transliterate_en_to_ar_token(brand_en)
        elif not brand_en and brand_ar:
            brand_en = transliterate_ar_to_en_token(brand_ar)
        elif brand_en and brand_ar:
            # Check for cross-language mismatch (e.g. user typed 'teja cafe' with stale 'مطعم صحراء')
            expected_ar = transliterate_en_to_ar_token(brand_en)
            try:
                from rapidfuzz import fuzz
                if expected_ar and fuzz.ratio(expected_ar, brand_ar) < 40:
                    # Stale or conflicting Arabic brand provided: realign to match English primary brand
                    brand_ar = expected_ar
            except Exception:
                pass

        core_en = brand_en or core_en
        core_ar = brand_ar or core_ar

        candidates: list[tuple[str, str, str]] = []  # (ar, en, source)
        cat_key = str(activity_category).lower().strip() if activity_category else ""
        resolved_category = CATEGORY_NAME_MAP.get(cat_key, activity_category or "General Business")

        # -------------------------------------------------------------
        # Step 1: Attempt LLM Suggestion Generation (~25 candidates)
        # -------------------------------------------------------------
        try:
            gateway = LlmGateway(session=self.session, redis_client=self.redis_client)
            batch = await gateway.generate_suggestions(
                request_id=request_id,
                channel=channel,
                name_ar=core_ar,
                name_en=core_en,
                activity_category=resolved_category,
                legal_form=legal_form,
                num_candidates=25,
            )
            await gateway.close()

            if batch and batch.suggestions:
                for s in batch.suggestions:
                    if s.name_ar and s.name_en:
                        # Enforce strict candidate relevance filter (Requirement 6)
                        if is_candidate_relevant(s.name_en, s.name_ar, brand_en, brand_ar):
                            candidates.append((s.name_ar.strip(), s.name_en.strip(), "llm"))
        except Exception as exc:
            logger.warning("suggestion_llm_failed_fallback", extra={"error": str(exc)})

        # -------------------------------------------------------------
        # Step 2: Category-Tailored Template Fallback (Ambiguity #5) if LLM produced few
        # -------------------------------------------------------------
        if len(candidates) < 10 and (brand_en or brand_ar):
            templates_to_use = (
                CATEGORY_TEMPLATES.get(cat_key)
                or (CATEGORY_TEMPLATES.get("4") if any(k in cat_key for k in ("rest", "food", "cafe", "4")) else None)
                or (CATEGORY_TEMPLATES.get("3") if any(k in cat_key for k in ("tech", "soft", "3")) else None)
                or (CATEGORY_TEMPLATES.get("1") if any(k in cat_key for k in ("trade", "comm", "1")) else None)
                or DEFAULT_TEMPLATES
            )
            for tmpl_ar, tmpl_en in templates_to_use:
                cand_ar = f"{brand_ar} {tmpl_ar}".strip()
                cand_en = f"{brand_en} {tmpl_en.title()}".strip()
                if is_candidate_relevant(cand_en, cand_ar, brand_en, brand_ar):
                    candidates.append((cand_ar, cand_en, "template"))

        if not candidates:
            return []

        # -------------------------------------------------------------
        # Step 3: Batch Normalize & Deduplicate
        # -------------------------------------------------------------
        seen_normalized: set[tuple[str, str]] = set()
        normalized_candidates: list[dict] = []

        for cand_ar, cand_en, source in candidates:
            norm_ar = normalize_arabic(cand_ar)
            norm_en = normalize_english(cand_en)
            key = (norm_ar, norm_en)
            if key in seen_normalized or not norm_ar or not norm_en:
                continue
            seen_normalized.add(key)
            normalized_candidates.append({
                "raw_ar": cand_ar,
                "raw_en": cand_en,
                "norm_ar": norm_ar,
                "norm_en": norm_en,
                "source": source,
            })

        # -------------------------------------------------------------
        # Step 4: Lexicon Screening (Drop any candidate triggering block/review)
        # Bounded cost (N8): single batch query instead of N individual queries
        # -------------------------------------------------------------
        from db.models import Lexicon
        stmt_lex = select(Lexicon).where(Lexicon.severity.in_(["block", "review"]))
        res_lex = await self.session.execute(stmt_lex)
        risk_entries = res_lex.scalars().all()
        risk_terms_ar = {r.normalized_term for r in risk_entries if r.lang in ("ar", "both")}
        risk_terms_en = {r.normalized_term for r in risk_entries if r.lang in ("en", "both")}

        clean_candidates: list[dict] = []
        for cand in normalized_candidates:
            words_ar = set(cand["norm_ar"].split())
            words_en = set(cand["norm_en"].split())
            if (words_ar & risk_terms_ar) or (words_en & risk_terms_en):
                continue
            clean_candidates.append(cand)

        if not clean_candidates:
            return []

        # -------------------------------------------------------------
        # Step 5: Reservation & Active Registry Check (F18 single set query)
        # -------------------------------------------------------------
        from db.models import TradeNameIndex

        norm_ar_list = [c["norm_ar"] for c in clean_candidates]
        norm_en_list = [c["norm_en"] for c in clean_candidates]

        stmt = select(TradeNameIndex.normalized_ar, TradeNameIndex.normalized_en).where(
            TradeNameIndex.status.in_(["active", "reserved"]),
            or_(
                TradeNameIndex.normalized_ar.in_(norm_ar_list),
                TradeNameIndex.normalized_en.in_(norm_en_list),
            ),
        )
        result = await self.session.execute(stmt)
        reserved_rows = result.fetchall()
        reserved_ar = {r[0] for r in reserved_rows}
        reserved_en = {r[1] for r in reserved_rows}

        unreserved: list[dict] = []
        for cand in clean_candidates:
            if cand["norm_ar"] in reserved_ar or cand["norm_en"] in reserved_en:
                continue
            unreserved.append(cand)

        # -------------------------------------------------------------
        # Step 6: Formatting (F8 Legal Form, F17 Uppercase English)
        # -------------------------------------------------------------
        final_suggestions: list[SuggestionItemDTO] = []
        for cand in unreserved[:limit]:
            final_ar = cand["raw_ar"]
            # F17: All English suggestion names returned in UPPER CASE
            final_en = cand["raw_en"].upper()

            # F8: Append legal form if specified and not already present
            if legal_form:
                lf_clean = legal_form.strip()
                if lf_clean and lf_clean.upper() not in final_en:
                    final_en = f"{final_en} {lf_clean.upper()}"
                if lf_clean and lf_clean not in final_ar:
                    final_ar = f"{final_ar} {lf_clean}"

            final_suggestions.append(
                SuggestionItemDTO(
                    name_ar=final_ar,
                    name_en=final_en,
                    score=1.0 if cand["source"] == "llm" else 0.85,
                    source=cand["source"],
                )
            )

        return final_suggestions
